// Phase-vocoder vocal shifter. Pure TypeScript: no AudioWorklet, no WASM,
// no native dependency, so it renders offline in browser without timing out.

const N = 2048;
const H = 512;

function fft(re: Float32Array, im: Float32Array): void {
  const n = re.length;
  for (let i = 1, j = 0; i < n; i++) {
    let bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j |= bit;
    if (i < j) {
      const tr = re[i]; re[i] = re[j]; re[j] = tr;
      const ti = im[i]; im[i] = im[j]; im[j] = ti;
    }
  }
  for (let len = 2; len <= n; len <<= 1) {
    const ang = (-2 * Math.PI) / len;
    const wr = Math.cos(ang);
    const wi = Math.sin(ang);
    const half = len >> 1;
    for (let i = 0; i < n; i += len) {
      let cr = 1;
      let ci = 0;
      for (let k = 0; k < half; k++) {
        const a = i + k;
        const b = a + half;
        const xr = re[b] * cr - im[b] * ci;
        const xi = re[b] * ci + im[b] * cr;
        re[b] = re[a] - xr;
        im[b] = im[a] - xi;
        re[a] += xr;
        im[a] += xi;
        const nr = cr * wr - ci * wi;
        ci = cr * wi + ci * wr;
        cr = nr;
      }
    }
  }
}

function ifft(re: Float32Array, im: Float32Array): void {
  const n = re.length;
  for (let i = 0; i < n; i++) im[i] = -im[i];
  fft(re, im);
  for (let i = 0; i < n; i++) {
    re[i] /= n;
    im[i] = -im[i] / n;
  }
}

function pitchShiftChannel(input: Float32Array, ratioAt: (pos: number) => number): Float32Array {
  const n = input.length;
  const win = new Float32Array(N);
  for (let i = 0; i < N; i++) win[i] = 0.5 - 0.5 * Math.cos((2 * Math.PI * i) / N);

  const frames = Math.max(1, Math.ceil(n / H));
  let total = 0;
  for (let m = 0; m < frames; m++) total += H * ratioAt(m * H);
  const outLen = Math.max(N * 2, Math.ceil(total) + N);
  const acc = new Float32Array(outLen);
  const wsum = new Float32Array(outLen);
  const re = new Float32Array(N);
  const im = new Float32Array(N);
  const prev = new Float32Array(N >> 1);
  const phase = new Float32Array(N >> 1);
  const step = new Float32Array(N >> 1);
  for (let k = 0; k < N >> 1; k++) step[k] = (2 * Math.PI * k * H) / N;

  let outPos = 0;
  for (let m = 0; m < frames; m++) {
    const inPos = m * H;
    for (let i = 0; i < N; i++) {
      const s = inPos + i;
      re[i] = s < n ? input[s] * win[i] : 0;
      im[i] = 0;
    }
    fft(re, im);
    const hs = Math.max(8, H * ratioAt(inPos));
    const half = N >> 1;
    for (let k = 0; k < half; k++) {
      const mag = Math.sqrt(re[k] * re[k] + im[k] * im[k]);
      const ph = Math.atan2(im[k], re[k]);
      let d = ph - prev[k] - step[k];
      d -= 2 * Math.PI * Math.round(d / (2 * Math.PI));
      const omega = (step[k] + d) / H;
      phase[k] += omega * hs;
      prev[k] = ph;
      const ar = mag * Math.cos(phase[k]);
      const ai = mag * Math.sin(phase[k]);
      re[k] = ar;
      im[k] = ai;
      re[N - 1 - k] = ar;
      im[N - 1 - k] = -ai;
    }
    im[0] = 0;
    im[half] = 0;
    ifft(re, im);
    const base = Math.round(outPos);
    for (let i = 0; i < N; i++) {
      const p = base + i;
      if (p >= outLen) break;
      acc[p] += re[i] * win[i];
      wsum[p] += win[i] * win[i];
    }
    outPos += hs;
    if (outPos + N >= outLen) break;
  }

  for (let i = 0; i < outLen; i++) if (wsum[i] > 1e-4) acc[i] /= wsum[i];

  const res = new Float32Array(n);
  const scale = outLen > 1 ? (outLen - 1) / Math.max(1, n - 1) : 1;
  for (let i = 0; i < n; i++) {
    const p = i * scale;
    const i0 = Math.floor(p);
    const f = p - i0;
    const a = i0 >= 0 && i0 < outLen ? acc[i0] : 0;
    const b = i0 + 1 >= 0 && i0 + 1 < outLen ? acc[i0 + 1] : a;
    res[i] = a + (b - a) * f;
  }
  return res;
}

export async function renderTuned(
  channels: Float32Array[],
  sampleRate: number,
  hop: number,
  curveCents: Float32Array,
  opts?: { formantCompensation?: boolean; tonalityHz?: number; onStage?: (s: string) => void; midiHint?: Float32Array; [k: string]: unknown }
): Promise<Float32Array[]> {
  const n = channels[0]?.length ?? 0;
  if (!n) return channels;
  const stage = opts?.onStage;
  const hopSafe = hop > 0 ? hop : H;
  const ratioAt = (pos: number): number => {
    const ci = Math.max(0, Math.min(curveCents.length - 1, Math.floor(pos / hopSafe)));
    const c = curveCents[ci];
    const cents = Number.isFinite(c) ? Math.max(-600, Math.min(600, c)) : 0;
    return Math.pow(2, cents / 1200);
  };
  try {
    const out: Float32Array[] = [];
    for (let c = 0; c < channels.length; c++) {
      stage?.("Engine: phase vocoder, channel " + (c + 1) + " of " + channels.length + "...");
      await new Promise((r) => setTimeout(r, 0));
      out.push(pitchShiftChannel(channels[c], ratioAt));
    }
    let peak = 0;
    for (const ch of out) {
      for (let i = 0; i < ch.length; i++) {
        const a = Math.abs(ch[i]);
        if (a > peak) peak = a;
      }
    }
    if (!Number.isFinite(peak) || peak < 1e-6) {
      stage?.("Engine: no output - returning dry vocal");
      return channels.map((c) => Float32Array.from(c));
    }
    stage?.("Engine: tuned vocal ready");
    return out;
  } catch {
    stage?.("Engine: failed - returning dry vocal");
    return channels.map((c) => Float32Array.from(c));
  }
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
