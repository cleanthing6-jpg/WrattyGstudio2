import modal

app = modal.App()

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install(
        "libsndfile1", "libx11-6", "libxext6", "libxinerama1",
        "libxrandr2", "libxrender1", "libxcursor1", "libfreetype6",
        "libasound2", "libxcomposite1",
    )
    .pip_install("pedalboard")
    .add_local_dir("vst_plugins", remote_path="/root/vst_plugins")
)

@app.function(image=image, timeout=120)
def check():
    import os
    p = "/root/vst_plugins/bigmaxzero/Big Max Zero.vst3/Contents/x86_64-linux/Big Max Zero.so"
    print("exists:", os.path.exists(p))
    print("size:", os.path.getsize(p))
    # Mark executable
    os.chmod(p, 0o755)
    try:
        from pedalboard import load_plugin
        plugin = load_plugin(p)
        print("LOADED OK")
        print("plugin:", plugin)
        return
    except Exception as e:
        print("LOAD FAILED:", str(e)[:400])
    # If load fails, try ldd to see missing deps
    import subprocess
    try:
        r = subprocess.run(["ldd", p], capture_output=True, text=True, timeout=10)
        print("--- ldd ---")
        print(r.stdout[:2000])
        print(r.stderr[:500])
    except Exception as e:
        print("ldd fail:", e)
