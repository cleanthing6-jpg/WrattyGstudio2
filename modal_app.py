
import modal

app = modal.App("wratty-mixer-mem")

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libsndfile1")
    .pip_install("numpy", "pedalboard", "requests")
    .add_local_dir("fx-api/api", remote_path="/root/api")
)


def _rss():
    try:
        with open("/proc/self/status") as f:
            for ln in f:
                if ln.startswith("VmRSS:"):
                    return int(ln.split()[1]) / 1024.0
    except Exception:
        pass
    return 0.0


@app.function(image=image, cpu=2.0, memory=8192, timeout=3600)
def mixer_mem(seconds: int = 180, nstem: int = 8):
    import sys, threading, time

    sys.path.insert(0, "/root/api")
    import numpy as np

    peak = {"mb": 0.0}
    stop = {"v": False}

    def sampler():
        while not stop["v"]:
            m = _rss()
            if m > peak["mb"]:
                peak["mb"] = m
            time.sleep(0.1)

    threading.Thread(target=sampler, daemon=True).start()

    out = {"base_mb": round(_rss(), 1), "seconds": seconds, "nstem": nstem}
    try:
        import auto

        sr = 48000
        n = sr * int(seconds)
        rng = np.random.default_rng(7)
        tt = np.arange(n, dtype=np.float64) / sr

        def mk(freq, amp):
            a = np.stack([
                amp * np.sin(2 * np.pi * freq * tt),
                amp * np.sin(2 * np.pi * freq * 1.01 * tt),
            ])
            a += 0.01 * rng.standard_normal((2, n))
            return a.astype(np.float32)

        roles = ["beat", "lead", "adlib", "backing"]
        groups = {r: [] for r in roles}
        for i in range(nstem):
            groups[roles[i % 4]].append(mk(60.0 + 40 * i, 0.5 / (1 + i)))
        out["loaded_mb"] = round(_rss(), 1)

        mixed, report = auto.mix(groups, sr)
        out["mode"] = report.get("mode")
        out["plate"] = report.get("plate")
        out["plate_error"] = report.get("plate_error")
        out["post_mix_mb"] = round(_rss(), 1)
        del groups

        lu = auto.integrated_lufs(mixed, sr)
        out["lufs"] = None if lu is None else round(lu, 2)

        loud, tp, brick = auto.limit(mixed, sr, -1.0)
        out["true_peak"] = round(tp, 2)
        out["brickwall"] = bool(brick)
        del mixed, loud
    except Exception as e:
        out["error"] = "%s: %s" % (type(e).__name__, str(e)[:400])

    stop["v"] = True
    time.sleep(0.3)
    out["peak_mb"] = round(peak["mb"], 1)
    print(out, flush=True)
    return out


@app.local_entrypoint()
def main(seconds: int = 180, nstem: int = 8):
    print(mixer_mem.remote(seconds, nstem))
