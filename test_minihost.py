import modal
app = modal.App()

image = (
    modal.Image.from_registry("ubuntu:24.04", add_python="3.12")
    .apt_install("libsndfile1", "libx11-6", "libxext6", "libxinerama1",
                 "libxrandr2", "libxrender1", "libxcursor1", "libfreetype6",
                 "libasound2t64", "libxcomposite1", "libcurl4", "libatomic1")
    .pip_install("minihost")
    .add_local_dir("vst_plugins", remote_path="/root/vst_plugins")
)

@app.function(image=image, timeout=120)
def check():
    import os, subprocess
    p = "/root/vst_plugins/bigmaxzero/Big Max Zero.vst3"
    print("exists:", os.path.exists(p))
    for sub in ["info", "params", "scan"]:
        print(f"=== minihost {sub} ===")
        try:
            r = subprocess.run(["minihost", sub, p],
                               capture_output=True, text=True, timeout=45)
            print("rc:", r.returncode)
            print("stdout:", (r.stdout or "")[:1200])
            print("stderr:", (r.stderr or "")[:600])
        except subprocess.TimeoutExpired:
            print("TIMEOUT after 45s")
        except Exception as e:
            print("EXC:", str(e)[:300])
