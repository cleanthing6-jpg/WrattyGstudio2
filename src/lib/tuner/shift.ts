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
  hop: number,
  curveCents: Float32Array,
  grain = 2048
): Float32Array[] {
  const n = channels[0]?.length ?? 0;
  const out = channels.map(() => new Float32Array(n));
  if (!n) return out;
  const half = grain >> 1;
  const twoPi = Math.PI * 2;
  let r = 1;
  for (let i = 0; i < n; i++) {
    const frame = Math.max(0, Math.min(curveCents.length - 1, Math.floor(i / hop)));
    const target = Math.pow(2, curveCents[frame] / 1200);
    r += (target - r) * 0.001;
    const t1 = (i % grain) / grain;
    const t2 = ((i + half) % grain) / grain;
    const d1 = (1 - r) * t1 * grain;
    const d2 = (1 - r) * t2 * grain;
    const w1 = 0.5 * (1 - Math.cos(twoPi * t1));
    const w2 = 0.5 * (1 - Math.cos(twoPi * t2));
    for (let c = 0; c < channels.length; c++) {
      out[c][i] = w1 * read(channels[c], i - d1) + w2 * read(channels[c], i - d2);
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
