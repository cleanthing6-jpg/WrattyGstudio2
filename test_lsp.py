import modal
app = modal.App()

image = (
    modal.Image.from_registry("ubuntu:24.04", add_python="3.12")
    .apt_install("libsndfile1", "libx11-6", "libxext6", "libxinerama1",
                 "libxrandr2", "libxrender1", "libxcursor1", "libfreetype6",
                 "libasound2t64", "libxcomposite1", "libcurl4", "libatomic1",
                 "lsp-plugins-vst3")
    .pip_install("pedalboard")
)

@app.function(image=image, timeout=180)
def check():
    import os, glob
    roots = ["/usr/lib/vst3", "/usr/lib/x86_64-linux-gnu/vst3",
             "/usr/local/lib/vst3", "/usr/lib/lsp-plugins"]
    found = []
    for r in roots:
        if os.path.isdir(r):
            for dp, _, fs in os.walk(r):
                for f in fs:
                    if f.endswith(".vst3") or (".vst3" in dp and f.endswith(".so")):
                        found.append(os.path.join(dp, f))
    print("found LSP plugins:", len(found))
    for p in found[:10]:
        print(" ", p)
    if not found:
        return
    from pedalboard import load_plugin
    for p in found[:5]:
        try:
            plugin = load_plugin(p)
            print("LOADED OK:", p)
            return
        except Exception as e:
            print("FAILED:", p, "->", str(e)[:200])
