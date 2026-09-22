"""ACE-Step generation step. Runs on the GPU backend.
We fill in the actual ACE-Step call when we're on Kaggle/Colab.
"""

def build_prompt(cond, style="afrobeats"):
    return (f"{style} instrumental, {cond['bpm']} bpm, key of {cond['key']}, "
            f"no vocals, no lead melody, leave space for vocals")

def generate(prompt, out_path="beat.wav"):
    # TODO: call ACE-Step inference here (wire on GPU box)
    raise NotImplementedError("Wire ACE-Step on the GPU box")
