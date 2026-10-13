import modal

app = modal.App()

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libsndfile1", "libx11-6", "libxext6", "libxinerama1",
                 "libxrandr2", "libxrender1", "libxcursor1", "libfreetype6",
                 "libasound2", "libxcomposite1")
    .pip_install("pedalboard")
)

@app.function(image=image, timeout=120)
def check():
    import os, subprocess, glob
    # We need to download TDR Limiter 6 GE Linux VST3
    # But since we can't download inside the test without internet access to the plugin site,
    # let's first check if there's a way to install it via apt or download it
    
    # Actually, let's just check what's available on the system and test loading a simple plugin
    # to confirm the base image works for VST3 loading
    
    # Test with a known-good plugin path - check if pedalboard can load anything
    from pedalboard import load_plugin
    
    # List available VST3 directories
    dirs = ["/usr/lib/vst3", "/usr/local/lib/vst3", "/usr/lib/x86_64-linux-gnu/vst3"]
    for d in dirs:
        print(f"checking {d}: exists={os.path.exists(d)}")
        if os.path.exists(d):
            print(f"  contents: {os.listdir(d)[:5]}")
    
    print("pedalboard version:", __import__('pedalboard').__version__)
    print("base image GLIBC check:")
    r = subprocess.run(["ldd", "--version"], capture_output=True, text=True)
    print(r.stdout.split('\n')[0] if r.stdout else "unknown")
    
    # Check if we can at least load a built-in pedalboard effect
    from pedalboard import Reverb, Compressor
    import numpy as np
    a = np.random.randn(2, 44100).astype(np.float32) * 0.1
    try:
        y = Reverb(room_size=0.5)(a, 44100)
        print("built-in Reverb works, shape:", y.shape)
    except Exception as e:
        print("built-in Reverb failed:", e)
    
    try:
        y = Compressor(threshold_db=-20, ratio=4.0)(a, 44100)
        print("built-in Compressor works, shape:", y.shape)
    except Exception as e:
        print("built-in Compressor failed:", e)
