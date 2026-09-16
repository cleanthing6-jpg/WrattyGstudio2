import modal

app = modal.App("wratty-smoke")
image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libsndfile1")
    .pip_install("numpy", "pedalboard")
)


@app.function(image=image, cpu=2.0, memory=4096, timeout=900)
def check():
    import numpy as np
    import pedalboard

    x = np.zeros((2, 48000 * 30), dtype=np.float32)
    pb = pedalboard.Pedalboard(
        [pedalboard.HighpassFilter(cutoff_frequency_hz=30)]
    )
    y = pb(x, 48000)
    with open("/proc/self/status") as f:
        rss = [ln for ln in f if ln.startswith("VmRSS:")][0].split()[1]
    return {
        "numpy": np.__version__,
        "pedalboard": pedalboard.__version__,
        "dsp_ok": bool(y.shape == x.shape),
        "rss_mb": round(int(rss) / 1024.0, 1),
    }


@app.local_entrypoint()
def main():
    print(check.remote())
