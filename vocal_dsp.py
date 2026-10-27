import numpy as np
import scipy.signal
import scipy.ndimage
import pyworld as pw

class PitchCorrector:
    def __init__(self, sample_rate=44100):
        self.sr = sample_rate
        
        self.note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        self.scale_intervals = {
            "Chromatic": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
            "Major": [0, 2, 4, 5, 7, 9, 11],
            "Natural Minor": [0, 2, 3, 5, 7, 8, 10],
            "Pentatonic Major": [0, 2, 4, 7, 9],
            "Pentatonic Minor": [0, 3, 5, 7, 10],
            "Blues": [0, 3, 5, 6, 7, 10]
        }

    def _hz_to_midi(self, f0):
        non_zero = (f0 > 0) & ~np.isnan(f0)
        midi = np.zeros_like(f0)
        midi[non_zero] = 69 + 12 * np.log2(f0[non_zero] / 440.0)
        return midi

    def _midi_to_hz(self, midi):
        return 440.0 * (2.0 ** ((midi - 69.0) / 12.0))

    def _get_scale_pitches(self, root_note: str, scale_type: str):
        root_note = root_note.upper().strip()
        root_val = self.note_names.index(root_note) if root_note in self.note_names else 0
        intervals = self.scale_intervals.get(scale_type, self.scale_intervals["Natural Minor"])
        
        allowed_midi = []
        for octave in range(1, 9):
            for interval in intervals:
                note_val = 12 * octave + root_val + interval
                if 24 <= note_val <= 108:
                    allowed_midi.append(note_val)
        return np.array(allowed_midi)

    def _shift_formants(self, sp, shift_factor):
        """
        Formant Designer: Warps the spectral envelope (sp) along 
        the frequency axis to alter throat resonance without changing pitch.
        """
        if shift_factor == 1.0 or shift_factor <= 0:
            return sp
        n_frames, n_bins = sp.shape
        shifted_sp = np.zeros_like(sp)
        freq_axis = np.linspace(0, 1, n_bins)
        
        for i in range(n_frames):
            new_freq_axis = freq_axis * shift_factor
            shifted_sp[i] = np.interp(freq_axis, new_freq_axis, sp[i], left=sp[i, 0], right=sp[i, -1])
        return shifted_sp

    def _process_pitch_contour(self, f0, allowed_midi_notes, retune_speed_ms, humanize, dead_zone_cents, frame_duration):
        """
        Industry-Standard Note Segmentation Engine:
        1. Identifies continuous voiced note segments.
        2. Calculates median MIDI pitch for each entire note segment.
        3. Snaps median note center to the scale grid.
        4. Smoothly interpolates shifts across note boundaries (Retune Speed).
        5. Preserves and re-adds natural vibrato on top.
        """
        corrected_f0 = np.copy(f0)
        voiced_mask = (f0 > 20) & ~np.isnan(f0)
        
        if not np.any(voiced_mask):
            return corrected_f0

        # Convert to MIDI space
        midi_contour = np.zeros_like(f0)
        midi_contour[voiced_mask] = 69 + 12 * np.log2(f0[voiced_mask] / 440.0)

        # 1. Extract Vibrato using Savitzky-Golay filter
        window_len = int(max(15, round(150.0 / frame_duration)))
        if window_len % 2 == 0:
            window_len += 1
        
        interpolated_midi = np.copy(midi_contour)
        valid_indices = np.where(voiced_mask)[0]
        if len(valid_indices) > window_len:
            interpolated_midi = np.interp(np.arange(len(f0)), valid_indices, midi_contour[valid_indices])
            note_center = scipy.signal.savgol_filter(interpolated_midi, window_length=window_len, polyorder=2)
            vibrato = midi_contour - note_center
        else:
            note_center = midi_contour
            vibrato = np.zeros_like(midi_contour)

        # 2. Note Segmentation: Find continuous voiced regions
        padded_mask = np.pad(voiced_mask.astype(int), (1, 1), 'constant')
        diff = np.diff(padded_mask)
        starts = np.where(diff == 1)[0]
        ends = np.where(diff == -1)[0]

        # 3. Calculate segment shifts
        frame_target_shift = np.zeros_like(f0)
        for start, end in zip(starts, ends):
            if end - start < 2:
                continue
            
            seg_center = note_center[start:end]
            median_midi = np.median(seg_center)
            
            # Find nearest allowed scale note
            nearest_idx = np.argmin(np.abs(allowed_midi_notes - median_midi))
            target_midi = allowed_midi_notes[nearest_idx]
            
            # Apply Dead Zone Tolerance on median note center
            cents_off = (median_midi - target_midi) * 100.0
            if abs(cents_off) <= dead_zone_cents:
                shift = 0.0
            else:
                shift = target_midi - median_midi
            
            frame_target_shift[start:end] = shift

        # 4. Smooth transitions between note segments over retune speed / transition time
        transition_frames = int(max(1, round(retune_speed_ms / frame_duration)))
        sigma = max(1.0, transition_frames / 2.0)
        smoothed_shift = scipy.ndimage.gaussian_filter1d(frame_target_shift, sigma=sigma)

        # Apply corrected center shift
        corrected_center = note_center + smoothed_shift

        # 5. Re-introduce natural vibrato scaled by humanize setting
        final_midi = corrected_center + vibrato * (1.0 - (humanize / 100.0))

        # Convert back to Hz
        corrected_f0[voiced_mask] = 440.0 * (2.0 ** ((final_midi[voiced_mask] - 69.0) / 12.0))
        corrected_f0[~voiced_mask] = 0.0

        return corrected_f0

    def generate_json_piano_roll(self, f0_contour, times):
        notes_array = []
        if len(f0_contour) == 0:
            return notes_array

        in_note = False
        start_time = 0.0
        accumulated_midi = []

        for idx, f0 in enumerate(f0_contour):
            t = times[idx]
            if f0 > 20 and not np.isnan(f0):
                midi_val = float(69 + 12 * np.log2(f0 / 440.0))
                if not in_note:
                    in_note = True
                    start_time = float(t)
                    accumulated_midi = [midi_val]
                else:
                    accumulated_midi.append(midi_val)
            else:
                if in_note:
                    end_time = float(t)
                    avg_midi = float(np.median(accumulated_midi))
                    notes_array.append({
                        "startTime": round(start_time, 3),
                        "endTime": round(end_time, 3),
                        "duration": round(end_time - start_time, 3),
                        "pitchMidi": round(avg_midi, 2),
                        "noteName": self.note_names[int(round(avg_midi)) % 12] + str(int(round(avg_midi) // 12 - 1))
                    })
                    in_note = False
                    accumulated_midi = []

        if in_note and len(accumulated_midi) > 0:
            end_time = float(times[-1])
            avg_midi = float(np.median(accumulated_midi))
            notes_array.append({
                "startTime": round(start_time, 3),
                "endTime": round(end_time, 3),
                "duration": round(end_time - start_time, 3),
                "pitchMidi": round(avg_midi, 2),
                "noteName": self.note_names[int(round(avg_midi)) % 12] + str(int(round(avg_midi) // 12 - 1))
            })

        return notes_array

    def process_audio(self, audio_data: np.ndarray, key="C", scale="Natural Minor", 
                      retune_speed=25.0, humanize=20.0, dead_zone=4.0, formant_shift=1.0):
        x = audio_data.astype(np.float64)
        if np.max(np.abs(x)) > 0:
            x = x / np.max(np.abs(x)) * 0.95

        # 1. Pitch Tracking via WORLD
        _f0, t = pw.dio(x, self.sr, frame_period=5.0) 
        f0 = pw.stonemask(x, _f0, t, self.sr)
        
        frame_duration = (len(x) / self.sr / len(f0)) * 1000.0 if len(f0) > 0 else 5.0

        # 2. Spectral Parameter Extraction & Formant Shift
        sp = pw.cheaptrick(x, f0, t, self.sr)
        ap = pw.d4c(x, f0, t, self.sr)
        sp = self._shift_formants(sp, formant_shift)

        # 3. Generate Piano Roll JSON Map for UI
        piano_roll_data = self.generate_json_piano_roll(f0, t)

        # 4. Note Segmentation & Scale Correction
        allowed_midi = self._get_scale_pitches(key, scale)
        corrected_f0 = self._process_pitch_contour(f0, allowed_midi, retune_speed, humanize, dead_zone, frame_duration)

        # 5. Vocoder Synthesis with Breath/Unvoiced Protection
        tuned_audio = pw.synthesize(corrected_f0, sp, ap, self.sr)

        # Crossfade dry audio for unvoiced/breath sections to eliminate robotic noise
        unvoiced_mask = (corrected_f0 <= 20) | np.isnan(corrected_f0)
        if len(tuned_audio) == len(x) and len(f0) > 0:
            blend_mask = unvoiced_mask.astype(float)
            hop_samples = int(len(x) / len(f0))
            if hop_samples < 1: hop_samples = 1
            blend_mask = np.repeat(blend_mask, hop_samples)[:len(x)]
            if len(blend_mask) < len(x):
                blend_mask = np.pad(blend_mask, (0, len(x) - len(blend_mask)), 'edge')
            
            tuned_audio = (1.0 - blend_mask) * tuned_audio + blend_mask * x[:len(tuned_audio)]

        return tuned_audio.astype(np.float32), piano_roll_data
