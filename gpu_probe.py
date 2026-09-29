import modal

app = modal.App("gpu-probe")


@app.function(gpu="T4", timeout=600)
def probe():
    import subprocess
    return subprocess.run(["nvidia-smi"], capture_output=True, text=True).stdout[:1500]


@app.local_entrypoint()
def main():
    print(probe.remote())
