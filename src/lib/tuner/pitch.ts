import { PitchDetector } from "pitchy";

export type Mode = "major" | "minor" | "chromatic";

export type TuneSettings = {
  root: number;      // 0=C .. 11=B
  mode: Mode;
  amount: number;    // 0..1 correction strength
  retuneMs: number;  // 10 hard, 40 balanced, 80 natural
  vibrato: number;   // 0..1 how much natural vibrato survives
};

export const DEFAULTS: TuneSettings = { root: 2, mode: "minor", amount: 0.75, retuneMs: 40, vibrato: 0.7 };

export const NOTE_NAMES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"];

const SCALES: Record<Mode, number[]> = {
  major: [0, 2, 4, 5, 7, 9, 11],
  minor: [0, 2, 3, 5, 7, 8, 10],
  chromatic: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11],
};

const FRAME = 2048;
const HOP = 512;
const CLARITY = 0.8;

const toMidi = (hz: number) => 69 + 12 * Math.log2(hz / 440);

export type Analysis = { midi: Float32Array; clarity: Float32Array; hop: number; frame: number };

export function analyseTrack(x: Float32Array, sampleRate: number): Analysis {
  const det = PitchDetector.forFloat32Array(FRAME);
  const win = new Float32Array(FRAME);
  const n = Math.max(1, Math.floor(Math.max(0, x.length - FRAME) / HOP) + 1);
  const midi = new Float32Array(n);
  const clarity = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    win.set(x.subarray(i * HOP, i * HOP + FRAME));
    const [hz, c] = det.findPitch(win, sampleRate);
    clarity[i] = c;
    midi[i] = hz > 0 && c >= CLARITY ? toMidi(hz) : NaN;
  }
  return { midi, clarity, hop: HOP, frame: FRAME };
}

function clean(midi: Float32Array): Float32Array {
  const out = Float32Array.from(midi);
  let last = NaN;
  for (let i = 0; i < out.length; i++) {
    if (Number.isNaN(out[i])) continue;
    if (!Number.isNaN(last)) {
      let best = out[i], bestD = Math.abs(out[i] - last);
      for (const c of [out[i] - 12, out[i] + 12]) {
        const d = Math.abs(c - last);
        if (d < bestD) { best = c; bestD = d; }
      }
      out[i] = best;
      if (Math.abs(out[i] - last) > 12) out[i] = last;
    }
    last = out[i];
  }
  const med = Float32Array.from(out);
  for (let i = 1; i < out.length - 1; i++) {
    const vals = [out[i - 1], out[i], out[i + 1]].filter((v) => !Number.isNaN(v)).sort((a, b) => a - b);
    med[i] = vals.length ? vals[Math.floor(vals.length / 2)] : NaN;
  }
  return med;
}

function snap(m: number, s: TuneSettings): number {
  const allowed = SCALES[s.mode].map((iv) => (s.root + iv) % 12);
  const base = Math.floor(m);
  let best = m, bestD = Infinity;
  for (let o = -1; o <= 1; o++) {
    const cand = base + o;
    const pc = ((cand % 12) + 12) % 12;
    if (!allowed.includes(pc)) continue;
    const d = Math.abs(cand - m);
    if (d < bestD) { best = cand; bestD = d; }
  }
  return best;
}

export function buildCurve(a: Analysis, sampleRate: number, s: TuneSettings): Float32Array {
  const m = clean(a.midi);
  const n = m.length;
  const trend = new Float32Array(n).fill(NaN);
  const w = Math.max(1, Math.round((0.15 * sampleRate) / a.hop));
  for (let i = 0; i < n; i++) {
    let sum = 0, cnt = 0;
    for (let j = Math.max(0, i - w); j <= Math.min(n - 1, i + w); j++) {
      if (!Number.isNaN(m[j])) { sum += m[j]; cnt++; }
    }
    if (cnt) trend[i] = sum / cnt;
  }
  const raw = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    if (Number.isNaN(m[i]) || a.clarity[i] < CLARITY) { raw[i] = 0; continue; }
    const t = Number.isNaN(trend[i]) ? m[i] : trend[i];
    const note = (snap(m[i], s) - m[i]) * (1 - s.vibrato) + (snap(t, s) - t) * s.vibrato;
    raw[i] = Math.max(-100, Math.min(100, note * 100 * s.amount));
  }
  const alpha = 1 - Math.exp(-(a.hop / sampleRate) / Math.max(0.001, s.retuneMs / 1000));
  const out = new Float32Array(n);
  let cur = 0;
  for (let i = 0; i < n; i++) { cur += alpha * (raw[i] - cur); out[i] = cur; }
  return out;
}
