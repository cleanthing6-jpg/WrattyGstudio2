"""Genre presets = starting points for the Settings dataclass. They encode common production practice
(retune speed / amount / how much natural movement survives); they are NOT validated by listening tests."""
from .control import Settings

PRESETS = {
    "transparent": dict(retune_ms=70, amount=0.75, flex_cents=18, humanize=0.6, vibrato_keep=1.0),
    "natural":     dict(retune_ms=55, amount=0.85, flex_cents=15, humanize=0.5, vibrato_keep=1.0),
    "rnb":         dict(retune_ms=45, amount=0.88, flex_cents=14, humanize=0.5, vibrato_keep=1.0),
    "gospel":      dict(retune_ms=50, amount=0.85, flex_cents=15, humanize=0.55, vibrato_keep=1.0),
    "afrobeats":   dict(retune_ms=28, amount=0.92, flex_cents=11, humanize=0.35, vibrato_keep=0.9),
    "afro_pop":    dict(retune_ms=22, amount=0.94, flex_cents=10, humanize=0.30, vibrato_keep=0.85),
    "amapiano":    dict(retune_ms=32, amount=0.90, flex_cents=12, humanize=0.40, vibrato_keep=0.95),
    "dancehall":   dict(retune_ms=24, amount=0.93, flex_cents=10, humanize=0.30, vibrato_keep=0.85),
    "hiphop":      dict(retune_ms=14, amount=0.97, flex_cents=8,  humanize=0.20, vibrato_keep=0.6),
    "trap_melodic":dict(retune_ms=8,  amount=1.00, flex_cents=5,  humanize=0.10, vibrato_keep=0.35),
    "hard":        dict(retune_ms=0,  amount=1.00, flex_cents=0,  humanize=0.0,  vibrato_keep=0.0, hysteresis_cents=12),
}

def make_settings(genre: str = "afrobeats", **overrides) -> Settings:
    if genre not in PRESETS:
        raise ValueError(f"unknown genre {genre!r}; choose from {sorted(PRESETS)}")
    d = dict(PRESETS[genre]); d.update(overrides)
    return Settings(**d)
