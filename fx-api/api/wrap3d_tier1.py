"""Tier-1 3D head-wrap — analytical HRTF + contralateral M/S engine."""
import numpy as np
import scipy.signal as signal


class Tier1Wrap3DEngine:
    def __init__(self, sample_rate=44100):
        self.sr = sample_rate

    def _biquad_to_sos(self, b, a):
        return np.array([[b[0], b[1], b[2],
                          a[0], a[1], a[2]]],
                        dtype=np.float32)

    def _analytical_hrtf_single_channel(self, x, azimuth_deg):
        N = len(x)
        freqs = np.fft.rfftfreq(N, d=1.0 / self.sr)
        X_fft = np.fft.rfft(x)
        head_radius, speed_of_sound = 0.0875, 343.0
        theta_l = np.radians(azimuth_deg + 90.0)
        theta_r = np.radians(azimuth_deg - 90.0)
        itd_l = (head_radius / speed_of_sound) * (np.sin(theta_l) + theta_l)
        itd_r = (head_radius / speed_of_sound) * (np.sin(theta_r) + theta_r)

        def calc_ild(theta, delay_val):
            alpha = 1.0 + 0.5 * np.cos(theta)
            mag = np.ones_like(freqs)
            mag[freqs < 500] = 1.0 + 0.1 * np.cos(theta)
            high = freqs >= 500
            mag[high] = (alpha + (freqs[high] / 3000.0) ** 2) / (1.0 + (freqs[high] / 3000.0) ** 2)
            notch = (freqs >= 8000) & (freqs <= 12000)
            mag[notch] *= (1.0 - 0.15 * np.abs(np.sin(theta)))
            return mag * np.exp(-1j * 2.0 * np.pi * freqs * delay_val)

        out_l = np.fft.irfft(X_fft * calc_ild(theta_l, itd_l), n=N)
        out_r = np.fft.irfft(X_fft * calc_ild(theta_r, itd_r), n=N)
        return out_l.astype(np.float32), out_r.astype(np.float32)

    def _vectorized_fractional_delay(self, sig, delay_ms_array):
        n = len(sig)
        idx = np.arange(n, dtype=np.float32)
        target = np.clip(idx - ((delay_ms_array * self.sr) / 1000.0), 0.0, n - 2.0)
        i0 = np.floor(target).astype(np.int32)
        fr = target - i0
        return (1.0 - fr) * sig[i0] + fr * sig[i0 + 1]

    def _vectorized_sliding_rms(self, sig, window_size):
        cs = np.cumsum(np.insert(sig ** 2, 0, 0.0))
        w_sum = cs[window_size:] - cs[:-window_size]
        pad = len(sig) - len(w_sum)
        padded = np.pad(w_sum, (pad // 2, pad - (pad // 2)), mode="edge")
        return np.sqrt(np.maximum(0.0, padded / window_size))

    def _oversampled_soft_clip(self, x, os_factor=4, ceiling=0.98, threshold_db=-3.0):
        if os_factor == 1:
            return self._knee_clip(x, ceiling, threshold_db)
        up = signal.resample_poly(x, os_factor, 1)
        return signal.resample_poly(self._knee_clip(up, ceiling, threshold_db), 1, os_factor)

    def _knee_clip(self, x, ceiling, threshold_db):
        t = 10.0 ** (threshold_db / 20.0)
        out = x.copy()
        mask = np.abs(x) > t
        if np.any(mask):
            out[mask] = np.sign(x[mask]) * (
                t + (ceiling - t) * np.tanh((np.abs(x[mask]) - t) / (ceiling - t)))
        return np.clip(out, -ceiling, ceiling)

    def process(self, vocal_signal, instrumental_signal=None, bpm=120.0, song_section="hook"):
        num_samples = len(vocal_signal)
        vocal_mono = vocal_signal.astype(np.float32)

        v_env = self._vectorized_sliding_rms(vocal_mono, max(2, int(self.sr * 0.01)))
        vocal_mono = np.where(v_env < 10.0 ** (-50.0 / 20.0), 0.0, vocal_mono).astype(np.float32)

        rms_vocal = max(1e-5, np.sqrt(np.mean(vocal_mono ** 2)))

        section_offsets = {"verse": -14.0, "hook": -11.0, "bridge": -17.0}
        target_offset_db = section_offsets.get(song_section.lower(), -14.0)
        if instrumental_signal is not None:
            rms_inst_db = 20.0 * np.log10(max(1e-5, np.sqrt(np.mean(instrumental_signal ** 2))))
            if rms_inst_db > -12.0:
                target_offset_db += 2.0
        target_wrap_lin = 10.0 ** (target_offset_db / 20.0)
        adaptive_scale = target_wrap_lin / rms_vocal

        wb = vocal_mono.copy()
        wb = signal.sosfilt(signal.butter(4, 180 / (self.sr / 2), btype="highpass", output="sos"), wb)

        w0_p = 2.0 * np.pi * 2500.0 / self.sr
        a_p = np.sin(w0_p) / (2.0 * 1.4)
        A_p = 10.0 ** (-3.5 / 40.0)
        wb = signal.sosfilt(self._biquad_to_sos(
            [1. + a_p * A_p, -2. * np.cos(w0_p), 1. - a_p * A_p],
            [1. + a_p / A_p, -2. * np.cos(w0_p), 1. - a_p / A_p]), wb)

        w0_a = 2.0 * np.pi * 11000.0 / self.sr
        A_a = 10.0 ** (2.0 / 40.0)
        al_a = np.sin(w0_a) / 2.0 * np.sqrt((A_a + 1.0 / A_a) * (1.0 / 0.707 - 1.0) + 2.0)
        wb = signal.sosfilt(self._biquad_to_sos(
            [A_a * ((A_a + 1.) - (A_a - 1.) * np.cos(w0_a) + 2. * np.sqrt(A_a) * al_a),
             2. * A_a * (A_a - 1. - (A_a + 1.) * np.cos(w0_a)),
             A_a * ((A_a + 1.) - (A_a - 1.) * np.cos(w0_a) - 2. * np.sqrt(A_a) * al_a)],
            [(A_a + 1.) + (A_a - 1.) * np.cos(w0_a) + 2. * np.sqrt(A_a) * al_a,
             -2. * (A_a - 1. + (A_a + 1.) * np.cos(w0_a)),
             (A_a + 1.) + (A_a - 1.) * np.cos(w0_a) - 2. * np.sqrt(A_a) * al_a]), wb)

        t = np.arange(num_samples, dtype=np.float32) / self.sr
        lfo_rate = bpm / 240.0
        wl_d = self._vectorized_fractional_delay(wb, 11.5 + 3.5 * np.sin(2.0 * np.pi * lfo_rate * t))
        wr_d = self._vectorized_fractional_delay(wb, 23.0 + 5.0 * np.cos(2.0 * np.pi * lfo_rate * t))

        s1_l, s1_r = self._analytical_hrtf_single_channel(wl_d, azimuth_deg=-30)
        s2_l, s2_r = self._analytical_hrtf_single_channel(wr_d, azimuth_deg=30)

        w_mid = 0.5 * ((s1_l + s2_l) + (s1_r + s2_r))
        w_side = 0.5 * ((s1_l + s2_l) - (s1_r + s2_r))

        w_side = signal.sosfilt(signal.butter(4, 250 / (self.sr / 2), btype="highpass", output="sos"), w_side)

        w0_m = 2.0 * np.pi * 3000.0 / self.sr
        a_m = np.sin(w0_m) / (2.0 * 1.0)
        A_m = 10.0 ** (2.0 / 40.0)
        w_mid = signal.sosfilt(self._biquad_to_sos(
            [1. + a_m * A_m, -2. * np.cos(w0_m), 1. - a_m * A_m],
            [1. + a_m / A_m, -2. * np.cos(w0_m), 1. - a_m / A_m]), w_mid)

        wl_c, wr_c = w_mid + w_side, w_mid - w_side
        c_mat = np.corrcoef(wl_c, wr_c)
        corr = c_mat[0, 1] if not np.isnan(c_mat[0, 1]) else 1.0
        if corr < 0.3:
            w_side *= max(0.1, (corr + 1.0) / 1.3)

        w_left, w_right = w_mid + w_side, w_mid - w_side
        d_env = np.where(v_env > rms_vocal * 0.7, 0.5, 1.0).astype(np.float32)
        bd, ad = signal.butter(1, 35.0 / (self.sr / 2.0), btype="lowpass")
        d_env = signal.lfilter(bd, ad, d_env)

        w_left *= (d_env * adaptive_scale)
        w_right *= (d_env * adaptive_scale)

        stereo_l = self._oversampled_soft_clip(vocal_mono + w_left, os_factor=4)
        stereo_r = self._oversampled_soft_clip(vocal_mono + w_right, os_factor=4)

        return np.vstack((stereo_l, stereo_r))


def apply_wrap(vocal_mono, sr=44100, instrumental_rms=-14.0, bpm=120.0, section="hook"):
    eng = Tier1Wrap3DEngine(sample_rate=int(sr))
    return eng.process(vocal_mono, instrumental_signal=None, bpm=float(bpm), song_section=section)
