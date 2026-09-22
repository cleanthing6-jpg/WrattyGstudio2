import sys, argparse, numpy as np, librosa

NOTES=['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
MAJ=np.array([6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88])
MIN=np.array([6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17])

def detect_bpm(y, sr):
    onset = librosa.onset.onset_strength(y=y, sr=sr)
    t = librosa.feature.tempo(onset_envelope=onset, sr=sr, aggregate=None)
    bpm = float(np.median(t))
    while bpm > 155: bpm /= 2      # fold octave errors
    while bpm < 75:  bpm *= 2
    return bpm

def analyze(path):
    y,sr=librosa.load(path,sr=22050,mono=True)
    bpm=detect_bpm(y,sr)
    ch=librosa.feature.chroma_cqt(y=y,sr=sr).mean(axis=1)
    best,sc=None,-2
    for i in range(12):
        for prof,m in ((MAJ,'major'),(MIN,'minor')):
            r=np.corrcoef(ch,np.roll(prof,i))[0,1]
            if r>sc: sc,best=r,(NOTES[i],m)
    return round(bpm),best[0],best[1]

def make_prompt(bpm,key,mode,style="afrobeats"):
    return (f"{style} instrumental, {bpm} bpm, key of {key} {mode}, "
            f"log drum, percussive groove, no vocals, no lead melody")

def generate(prompt,out,duration):
    from acestep.pipeline_ace_step import ACEStepPipeline
    pipe=ACEStepPipeline(checkpoint_dir="",dtype="bfloat16",
        torch_compile=False,cpu_offload=False,overlapped_decode=False)
    pipe(audio_duration=duration,prompt=prompt,lyrics="",
        infer_step=60,guidance_scale=15.0,scheduler_type="euler",
        cfg_type="apg",omega_scale=10.0,manual_seeds="42",
        guidance_interval=0.5,guidance_interval_decay=0.0,min_guidance_scale=3.0,
        use_erg_tag=True,use_erg_lyric=False,use_erg_diffusion=True,
        oss_steps="",guidance_scale_text=0.0,guidance_scale_lyric=0.0,
        save_path=out)
    return out

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("vocal")
    ap.add_argument("--bpm", type=int, default=None)
    ap.add_argument("--key", default=None)
    ap.add_argument("--mode", default=None)
    ap.add_argument("--duration", type=int, default=60)
    ap.add_argument("--out", default="beat.wav")
    a=ap.parse_args()
    dbpm,dkey,dmode=analyze(a.vocal)
    bpm=a.bpm or dbpm; key=a.key or dkey; mode=a.mode or dmode
    prompt=make_prompt(bpm,key,mode)
    print(f"auto-detected: {dbpm} bpm | {dkey} {dmode}  → using {bpm}")
    generate(prompt,a.out,a.duration)
    print("saved:",a.out)
