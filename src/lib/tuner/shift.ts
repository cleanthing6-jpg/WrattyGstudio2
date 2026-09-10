const read = (x: Float32Array, pos: number): number => {
  const len = x.length;
  if (len === 0) return 0;
  if (pos <= 0) return x[0];
  if (pos >= len - 1) return x[len - 1];
  const i = Math.floor(pos);
  const f = pos - i;
  return x[i] * (1 - f) + x[i + 1] * f;
};

export function applyCurve(
  channels: Float32Array[],
  sampleRate: number,
  hop: number,
  curveCents: Float32Array,
  midiHint?: Float32Array,
  taps = 4
): Float32Array[] {
  const n = channels[0]?.length ?? 0;
  const out = channels.map(() => new Float32Array(n));
  if (!n) return out;
  const twoPi = Math.PI * 2;
  const kPeriods = 8;
  const norm = 2 / taps;
  const offsets = new Float32Array(taps);
  for (let j = 0; j < taps; j++) offsets[j] = j / taps;
  let r = 1;
  let period = sampleRate / 220;
  let grain = period * kPeriods;
  let phase = 0;
  for (let i = 0; i < n; i++) {
    const frame = Math.max(0, Math.min(curveCents.length - 1, Math.floor(i / hop)));
    const target = Math.pow(2, curveCents[frame] / 1200);
    r += (target - r) * 0.004;
    if (midiHint && frame < midiHint.length) {
      const m = midiHint[frame];
      if (!Number.isNaN(m)) {
        const hz = 440 * Math.pow(2, (m - 69) / 12);
        if (hz > 60 && hz < 1200) {
          const p = sampleRate / hz;
          period += (p - period) * 0.05;
          grain += (period * kPeriods - grain) * 0.05;
          if (grain < 1024) grain = 1024;
          if (grain > 8192) grain = 8192;
        }
      }
    }
    phase += 1 / grain;
    if (phase >= 1) phase -= 1;
    for (let j = 0; j < taps; j++) {
      let t = phase + offsets[j];
      if (t >= 1) t -= 1;
      const d = (1 - r) * t * grain;
      const w = norm * 0.5 * (1 - Math.cos(twoPi * t));
      for (let c = 0; c < channels.length; c++) {
        out[c][i] += w * read(channels[c], i - d);
      }
    }
  }
  return out;
}

export function limitPeak(channels: Float32Array[], ceiling = 0.99): Float32Array[] {
  let peak = 0;
  for (const ch of channels) {
    for (let i = 0; i < ch.length; i++) {
      const a = Math.abs(ch[i]);
      if (a > peak) peak = a;
    }
  }
  if (peak <= ceiling || peak === 0) return channels;
  const g = ceiling / peak;
  for (const ch of channels) {
    for (let i = 0; i < ch.length; i++) ch[i] *= g;
  }
  return channels;
}
