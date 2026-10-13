import modal
app = modal.App()

image = (
    modal.Image.from_registry("ubuntu:24.04", add_python="3.12")
    .apt_install("libsndfile1", "libx11-6", "libxext6", "libxinerama1",
                 "libxrandr2", "libxrender1", "libxcursor1", "libfreetype6",
                 "libasound2t64", "libxcomposite1", "libcurl4", "libatomic1")
    .pip_install("pedalboard")
    .add_local_dir("vst_plugins", remote_path="/root/vst_plugins")
)

@app.function(image=image, timeout=120)
def check():
    import os, subprocess
    p = "/root/vst_plugins/bigmaxzero/Big Max Zero.vst3/Contents/x86_64-linux/Big Max Zero.so"
    print("exists:", os.path.exists(p))
    os.chmod(p, 0o755)
    r = subprocess.run(["ldd", "--version"], capture_output=True, text=True)
    print("GLIBC:", r.stdout.split("\n")[0])
    try:
        from pedalboard import load_plugin
        plugin = load_plugin(p)
        print("BIGMAX LOADED OK")
        print("plugin:", plugin)
        print("has params:", [a for a in dir(plugin) if not a.startswith('_')][:15])
    except Exception as e:
        print("LOAD FAILED:", str(e)[:400])
