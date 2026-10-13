import numpy as np


def _db_to_lin(db):
    return 10.0 ** (db / 20.0)


def opto_compress(x, sr,
                  threshold_db=-20.0,
                  ratio=3.0,
                  attack_ms=10.0,
                  release_fast_ms=100.0,
                  release_slow_ms=600.0,
                  fast_weight=0.55,
                  knee_db=6.0,
                  makeup_db=0.0):
    a = np.asarray(x, dtype=np.float64)
    if a.ndim == 1:
        a = a[None, :]
    if a.shape[1] < 64:
        return x, {"note": "too short"}
    peak = np.max(np.abs(a), axis=0)
    atk_coef = float(np.exp(-1.0 / max(1.0, sr * attack_ms / 1000.0)))
    rel_fast = float(np.exp(-1.0 / max(1.0, sr * release_fast_ms / 1000.0)))
    rel_slow = float(np.exp(-1.0 / max(1.0, sr * release_slow_ms / 1000.0)))
    n = peak.shape[0]
    env_fast = np.empty(n, dtype=np.float64)
    env_slow = np.empty(n, dtype=np.float64)
    ef = 0.0
    es = 0.0
    for i in range(n):
        s = peak[i]
        if s > ef:
            ef = s + atk_coef * (ef - s)
        else:
            ef = s + rel_fast * (ef - s)
        if s > es:
            es = s + atk_coef * (es - s)
        else:
            es = s + rel_slow * (es - s)
        env_fast[i] = ef
        env_slow[i] = es
    env = np.maximum(env_fast, env_slow * fast_weight + env_fast * (1.0 - fast_weight))
    env_db = 20.0 * np.log10(env + 1e-12)
    over = env_db - threshold_db
    gr_db = np.zeros_like(over)
    knee = (over > -knee_db) & (over <= 0.0)
    high = over > 0.0
    gr_db[knee] = -(over[knee] + knee_db) ** 2 / (2.0 * knee_db) * (1.0 - 1.0 / ratio)
    gr_db[high] = -(over[high] * (1.0 - 1.0 / ratio))
    gain = _db_to_lin(gr_db + makeup_db)
    y = (a * gain[None, :]).astype(np.float32)
    info = {
        "ratio": ratio,
        "threshold_db": threshold_db,
        "max_gr_db": round(float(np.min(gr_db)), 2),
        "avg_gr_db": round(float(np.mean(gr_db)), 2),
    }
    return y, info
