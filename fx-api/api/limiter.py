"""ProductionMasteringLimiter — user's original design, bugs fixed."""
import numpy as np
def _firwin(num_taps, cutoff_norm, beta=13.0):
    n = np.arange(num_taps) - (num_taps - 1) / 2.0
    h = np.sinc(2.0 * cutoff_norm * n) * np.kaiser(num_taps, beta)
    return (h / h.sum()).astype(np.float32)
from numba import njit, float32, int32


@njit(float32[:, :](float32[:, :], float32, float32, float32, float32, float32, float32,
                    float32[:], float32[:], float32[:], float32[:],
                    int32, int32, float32, float32, float32, float32, float32),
      fastmath=True, cache=True)
def _limiter_hot_loop(os_ms, ceiling_linear, coef_transient_attack, coef_sustain_attack,
                      rel_slow, rel_fast, ms_link,
                      buf_M, buf_S, env_states, sc_states,
                      num_os_samples, buf_len,
                      b0, b1, b2, a1, a2):
    sc_v1_M = sc_states[0]; sc_v2_M = sc_states[1]
    sc_v1_S = sc_states[2]; sc_v2_S = sc_states[3]
    env_transient_M = env_states[0]; env_sustain_M = env_states[1]; master_env_M = env_states[2]
    env_transient_S = env_states[3]; env_sustain_S = env_states[4]; master_env_S = env_states[5]
    idx = int32(env_states[6])
    os_ms_output = np.zeros(os_ms.shape, dtype=np.float32)
    for i in range(num_os_samples):
        s_M = os_ms[0, i]; s_S = os_ms[1, i]
        sc_filtered_M = b0 * s_M + sc_v1_M
        sc_v1_M = b1 * s_M - a1 * sc_filtered_M + sc_v2_M
        sc_v2_M = b2 * s_M - a2 * sc_filtered_M
        sc_filtered_S = b0 * s_S + sc_v1_S
        sc_v1_S = b1 * s_S - a1 * sc_filtered_S + sc_v2_S
        sc_v2_S = b2 * s_S - a2 * sc_filtered_S
        abs_M = abs(sc_filtered_M); abs_S = abs(sc_filtered_S)
        max_peak = max(abs_M, abs_S)
        det_M = (abs_M * (1.0 - ms_link)) + (max_peak * ms_link)
        det_S = (abs_S * (1.0 - ms_link)) + (max_peak * ms_link)
        if det_M > env_transient_M: env_transient_M = det_M
        else: env_transient_M = det_M + coef_transient_attack * (env_transient_M - det_M)
        if det_M > env_sustain_M: env_sustain_M = det_M + coef_sustain_attack * (env_sustain_M - det_M)
        else: env_sustain_M = det_M + rel_slow * (env_sustain_M - det_M)
        curr_rel_M = rel_fast if env_transient_M > (env_sustain_M * 1.65) else rel_slow
        target_env_M = max(env_transient_M, env_sustain_M)
        if target_env_M > master_env_M: master_env_M = target_env_M
        else: master_env_M = target_env_M + curr_rel_M * (master_env_M - target_env_M)
        if det_S > env_transient_S: env_transient_S = det_S
        else: env_transient_S = det_S + coef_transient_attack * (env_transient_S - det_S)
        if det_S > env_sustain_S: env_sustain_S = det_S + coef_sustain_attack * (env_sustain_S - det_S)
        else: env_sustain_S = det_S + rel_slow * (env_sustain_S - det_S)
        curr_rel_S = rel_fast if env_transient_S > (env_sustain_S * 1.65) else rel_slow
        target_env_S = max(env_transient_S, env_sustain_S)
        if target_env_S > master_env_S: master_env_S = target_env_S
        else: master_env_S = target_env_S + curr_rel_S * (master_env_S - target_env_S)
        g_red_M = ceiling_linear / master_env_M if master_env_M > ceiling_linear else 1.0
        g_red_S = ceiling_linear / master_env_S if master_env_S > ceiling_linear else 1.0
        delayed_M = buf_M[idx]; delayed_S = buf_S[idx]
        buf_M[idx] = s_M; buf_S[idx] = s_S
        idx = (idx + 1) % buf_len
        os_ms_output[0, i] = delayed_M * g_red_M
        os_ms_output[1, i] = delayed_S * g_red_S
    sc_states[0], sc_states[1], sc_states[2], sc_states[3] = sc_v1_M, sc_v2_M, sc_v1_S, sc_v2_S
    env_states[0], env_states[1], env_states[2] = env_transient_M, env_sustain_M, master_env_M
    env_states[3], env_states[4], env_states[5] = env_transient_S, env_sustain_S, master_env_S
    env_states[6] = float32(idx)
    return os_ms_output


class ProductionMasteringLimiter:
    def __init__(self, sample_rate: int = 44100, lookahead_ms: float = 2.0, oversampling: int = 4):
        self.sample_rate = sample_rate
        self.os_factor = oversampling
        self.os_sample_rate = float(sample_rate * self.os_factor)
        self.lookahead_samples = max(1, int((lookahead_ms / 1000.0) * self.os_sample_rate))
        self.delay_buffer_M = np.zeros(self.lookahead_samples, dtype=np.float32)
        self.delay_buffer_S = np.zeros(self.lookahead_samples, dtype=np.float32)
        self.env_states = np.zeros(7, dtype=np.float32)
        self.sc_states = np.zeros(4, dtype=np.float32)
        self.coef_transient_attack = np.float32(np.exp(-1.0 / (0.002 * self.os_sample_rate)))
        self.coef_sustain_attack = np.float32(np.exp(-1.0 / (0.025 * self.os_sample_rate)))
        num_taps = 192
        cutoff_freq = (sample_rate / 2.0) / (self.os_sample_rate / 2.0)
        self.fir_coeffs = _firwin(num_taps, cutoff_freq, beta=13.0)
        self.zi_os_M = np.zeros(len(self.fir_coeffs) - 1, dtype=np.float32)
        self.zi_os_S = np.zeros(len(self.fir_coeffs) - 1, dtype=np.float32)
        self.zi_ds_M = np.zeros(len(self.fir_coeffs) - 1, dtype=np.float32)
        self.zi_ds_S = np.zeros(len(self.fir_coeffs) - 1, dtype=np.float32)
        self.cached_sc_freq = -1.0
        self.b0 = np.float32(0.0); self.b1 = np.float32(0.0); self.b2 = np.float32(0.0)
        self.a1 = np.float32(0.0); self.a2 = np.float32(0.0)
    def _precompute_sc_coefficients(self, cutoff: float):
        if cutoff == self.cached_sc_freq:
            return
        w0 = 2.0 * np.pi * cutoff / self.os_sample_rate
        cos_w0 = np.cos(w0)
        alpha = np.sin(w0) / (2.0 * 0.707)
        a0 = 1.0 + alpha
        self.b0 = np.float32((1.0 + cos_w0) / 2.0 / a0)
        self.b1 = np.float32(-(1.0 + cos_w0) / a0)
        self.b2 = np.float32((1.0 + cos_w0) / 2.0 / a0)
        self.a1 = np.float32(-2.0 * cos_w0 / a0)
        self.a2 = np.float32((1.0 - alpha) / a0)
        self.cached_sc_freq = cutoff

    def _oversample_block(self, ms_block: np.ndarray) -> np.ndarray:
        num_samples = ms_block.shape[1]
        stuffed_M = np.zeros(num_samples * self.os_factor, dtype=np.float32)
        stuffed_S = np.zeros(num_samples * self.os_factor, dtype=np.float32)
        stuffed_M[::self.os_factor] = ms_block[0] * float(self.os_factor)
        stuffed_S[::self.os_factor] = ms_block[1] * float(self.os_factor)
        padM = np.concatenate([self.zi_os_M, stuffed_M])
        padS = np.concatenate([self.zi_os_S, stuffed_S])
        out_M = np.convolve(padM, self.fir_coeffs, mode='valid').astype(np.float32)
        out_S = np.convolve(padS, self.fir_coeffs, mode='valid').astype(np.float32)
        self.zi_os_M = padM[-len(self.fir_coeffs) + 1:].copy()
        self.zi_os_S = padS[-len(self.fir_coeffs) + 1:].copy()
        return np.array([out_M, out_S], dtype=np.float32)

    def _downsample_block(self, os_ms_block: np.ndarray) -> np.ndarray:
        padM = np.concatenate([self.zi_ds_M, os_ms_block[0]])
        padS = np.concatenate([self.zi_ds_S, os_ms_block[1]])
        filt_M = np.convolve(padM, self.fir_coeffs, mode='valid')
        filt_S = np.convolve(padS, self.fir_coeffs, mode='valid')
        self.zi_ds_M = padM[-len(self.fir_coeffs) + 1:].copy()
        self.zi_ds_S = padS[-len(self.fir_coeffs) + 1:].copy()
        return np.array([filt_M[::self.os_factor], filt_S[::self.os_factor]], dtype=np.float32)
    def process(self, stereo_signal: np.ndarray, input_gain_db: float, ceiling_db: float,
                release_ms: float, sc_hpf_freq: float = 120.0, ms_link: float = 0.85,
                bit_depth: int = 24) -> np.ndarray:
        stereo_signal = np.ascontiguousarray(stereo_signal, dtype=np.float32)
        if stereo_signal.ndim != 2 or stereo_signal.shape[0] != 2 or stereo_signal.size == 0:
            raise ValueError("Input must be stereo (2,N) and non-empty")
        if not np.isfinite(stereo_signal).all():
            raise ValueError("Input contains NaN or Inf")
        sc_hpf_freq = max(10.0, min(sc_hpf_freq, self.sample_rate * 0.45))
        gain_linear = np.float32(10.0 ** (input_gain_db / 20.0))
        ceiling_linear = np.float32(10.0 ** (ceiling_db / 20.0))
        self._precompute_sc_coefficients(sc_hpf_freq)
        boosted = stereo_signal * gain_linear
        mid_ch = 0.5 * (boosted[0] + boosted[1])
        side_ch = 0.5 * (boosted[0] - boosted[1])
        os_ms = self._oversample_block(np.array([mid_ch, side_ch], dtype=np.float32))
        num_os_samples = os_ms.shape[1]
        release_sec = release_ms / 1000.0
        rel_slow = np.float32(np.exp(-1.0 / (release_sec * self.os_sample_rate)))
        rel_fast = np.float32(np.exp(-1.0 / ((release_sec * 0.15) * self.os_sample_rate)))
        os_ms_output = _limiter_hot_loop(
            os_ms, ceiling_linear,
            self.coef_transient_attack, self.coef_sustain_attack,
            rel_slow, rel_fast, np.float32(ms_link),
            self.delay_buffer_M, self.delay_buffer_S,
            self.env_states, self.sc_states,
            np.int32(num_os_samples), np.int32(self.lookahead_samples),
            self.b0, self.b1, self.b2, self.a1, self.a2,
        )
        downsampled_ms = self._downsample_block(os_ms_output)
        final_stereo = np.zeros_like(downsampled_ms)
        final_stereo[0] = downsampled_ms[0] + downsampled_ms[1]
        final_stereo[1] = downsampled_ms[0] - downsampled_ms[1]
        peak_lr = max(float(np.max(np.abs(final_stereo[0]))), float(np.max(np.abs(final_stereo[1]))))
        ceiling_f = float(ceiling_linear)
        if peak_lr > 0.5:
            final_stereo *= ceiling_f / peak_lr
        return final_stereo


# Alias for backward-compat imports (mix.py:9)
Limiter = ProductionMasteringLimiter
