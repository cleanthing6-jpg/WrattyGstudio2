import numpy as np
import scipy.signal
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
        if root_note in self.note_names:
            root_val = self.note_names.index(root_note)
        else:
            root_val = 0
        intervals = self.scale_intervals.get(scale_type, self.scale_intervals["Natural Minor"])
        allowed_midi = []
        for octave in range(1, 9):
            for interval in intervals:
                note_val = 12 * octave + root_val + interval
                if 24 <= note_val <= 108:
                    allowed_midi.append(note_val)
        return np.array(allowed_midi)

    def _snap_to_target(self, f0_contour, allowed_midi_notes, retune_speed_ms, humanize, dead_zone_cents, frame_duration=5.0):
        corrected_f0 = np.copy(f0_contour)
        retune_speed_ms = max(1.0, retune_speed_ms)
        alpha = 1.0 - np.exp(-frame_duration / retune_speed_ms)

        for i in range(len(f0_contour)):
            f0 = f0_contour[i]
            if f0 <= 20 or np.isnan(f0):
                continue
            current_midi = 69 + 12 * np.log2(f0 / 440.0)
            diffs = allowed_midi_notes - current_midi
            nearest_idx = np.argmin(np.abs(diffs))
            target_midi = allowed_midi_notes[nearest_idx]
            cents_off = (current_midi - target_midi) * 100.0
            if abs(cents_off) <= dead_zone_cents:
                corrected_f0[i] = f0
                continue
            target_hz = self._midi_to_hz(target_midi)
            effective_alpha = alpha * (1.0 - (humanize / 100.0) * min(1.0, abs(cents_off) / 100.0))
            effective_alpha = np.clip(effective_alpha, 0.0, 1.0)
            corrected_f0[i] = f0 + effective_alpha * (target_hz - f0)
        return corrected_f0

    def generate_json_piano_roll(self, f0_contour, times):
        notes_array = []
        if len(f0_contour) == 0: return notes_array
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
                    notes_array.append({"startTime": round(start_time, 3), "endTime": round(end_time, 3), "duration": round(end_time - start_time, 3), "pitchMidi": round(avg_midi, 2), "noteName": self.note_names[int(round(avg_midi)) % 12] + str(int(round(avg_midi) // 12 - 1))})
                    in_note = False
                    accumulated_midi = []
        if in_note and len(accumulated_midi) > 0:
            end_time = float(times[-1])
            avg_midi = float(np.median(accumulated_midi))
            notes_array.append({"startTime": round(start_time, 3), "endTime": round(end_time, 3), "duration": round(end_time - start_time, 3), "pitchMidi": round(avg_midi, 2), "noteName": self.note_names[int(round(avg_midi)) % 12] + str(int(round(avg_midi) // 12 - 1))})
        return notes_array

    def process_audio(self, audio_data: np.ndarray, key="C", scale="Natural Minor", retune_speed=25.0, humanize=20.0, dead_zone=4.0):
        x = audio_data.astype(np.float64)
        if np.max(np.abs(x)) > 0:
            x = x / np.max(np.abs(x)) * 0.95
        _f0, t = pw.dio(x, self.sr, frame_period=5.0) 
        f0 = pw.stonemask(x, _f0, t, self.sr)
        frame_duration = (len(x) / self.sr / len(f0)) * 1000.0 if len(f0) > 0 else 5.0
        sp = pw.cheaptrick(x, f0, t, self.sr)
        ap = pw.d4c(x, f0, t, self.sr)
        piano_roll_data = self.generate_json_piano_roll(f0, t)
        allowed_midi = self._get_scale_pitches(key, scale)
        corrected_f0 = self._snap_to_target(f0, allowed_midi, retune_speed, humanize, dead_zone, frame_duration)
        tuned_audio = pw.synthesize(corrected_f0, sp, ap, self.sr)
        return tuned_audio.astype(np.float32), piano_roll_data
