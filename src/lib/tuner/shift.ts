import SignalsmithStretch from "signalsmith-stretch";

type StretchConfig = {
  output?: number; active?: boolean; input?: number; rate?: number;
  semitones?: number; tonalityHz?: number; formantSemitones?: number;
  formantCompensation?: boolean; formantBaseHz?: number;
  loopStart?: number; loopEnd?: number;
};

type StretchNode = AudioNode & {
  schedule: (c: StretchConfig) => void;
  start: (when?: number) => void;
  stop: (when?: number) => void;
  addBuffers: (buffers: Float32Array[]) => Promise<number>;
  dropBuffers: (toSeconds?: number) => Promise<unknown>;
  latency: () => number;
  configure: (c: { blockMs?: number; intervalMs?: number; splitComputation?: boolean; preset?: string }) => void;
  inputTime: number;
};

function padTo(x: Float32Array, n: number): Float32Array {
  if (x.length >= n) return x;
  const o = new Float32Array(n);
  o.set(x);
  return o;
}

function withTimeout<T>(p: Promise<T>, ms: number, label: string): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const t = setTimeout(() => reject(new Error(label + " timed out after " + Math.round(ms / 1000) + "s")), ms);
    p.then((v) => { clearTimeout(t); resolve(v); }, (e) => { clearTimeout(t); reject(e); });
  });
}

async function makeNode(ctx: BaseAudioContext, channels: number): Promise<StretchNode> {
  const f = SignalsmithStretch as unknown as (
    c: BaseAudioContext,
    o?: AudioWorkletNodeOptions
  ) => Promise<StretchNode>;
  try {
    return await f(ctx, { numberOfInputs: 0, numberOfOutputs: 1, outputChannelCount: [channels] });
  } catch {
    return await f(ctx);
  }
}

function bestLag(a: Float32Array, b: Float32Array, maxLag: number): number {
  const len = Math.min(a.length, b.length);
  let best = 0;
  let bestScore = -Infinity;
  for (let lag = -maxLag; lag <= maxLag; lag++) {
    let sum = 0;
    let cnt = 0;
    for (let i = 0; i < len; i += 32) {
      const j = i + lag;
      if (j < 0 || j >= len) continue;
      sum += a[i] * b[j];
      cnt++;
    }
    if (!cnt) continue;
    const s = sum / cnt;
    if (s > bestScore) { bestScore = s; best = lag; }
  }
  return best;
}

export async function renderTuned(
  channels: Float32Array[],
  sampleRate: number,
  hop: number,
  curveCents: Float32Array,
  opts?: { formantCompensation?: boolean; tonalityHz?: number; onStage?: (s: string) => void }
): Promise<Float32Array[]> {
  const ch = Math.max(1, channels.length);
  const n = channels[0]?.length ?? 0;
  if (!n) return channels;
  const stage = opts?.onStage;

  const safe = channels.map((c) => padTo(c, n));
  const tail = Math.ceil(sampleRate * 0.4);
  const ctx = new OfflineAudioContext(ch, n + tail, sampleRate);

  stage?.("Engine: loading worklet...");
  const node = await withTimeout(makeNode(ctx, ch), 25000, "Worklet load");

  try { node.configure({ blockMs: 120 }); } catch {}

  stage?.("Engine: worklet ready, loading audio...");
  await withTimeout(node.addBuffers(safe), 25000, "addBuffers");

  node.connect(ctx.destination);
  node.start(0);

  const first = curveCents.length ? curveCents[0] / 100 : 0;
  node.schedule({
    output: 0,
    active: true,
    input: 0,
    rate: 1,
    semitones: Number.isFinite(first) ? first : 0,
    tonalityHz: opts?.tonalityHz ?? 8000,
    formantCompensation: opts?.formantCompensation ?? true,
    formantBaseHz: 0,
  });

  const step = hop / sampleRate;
  const MAX = 20000;
  const stride = Math.max(1, Math.ceil(curveCents.length / MAX));
  for (let i = stride; i < curveCents.length; i += stride) {
    const c = curveCents[i];
    if (!Number.isFinite(c)) continue;
    node.schedule({ output: i * step, rate: 1, semitones: Math.max(-6, Math.min(6, c / 100)) });
  }

  stage?.("Engine: rendering tuned vocal...");
  const rendered = await withTimeout(ctx.startRendering(), 180000, "Offline render");

  const maxLag = Math.round(sampleRate * 0.05);
  const lag = bestLag(safe[0], rendered.getChannelData(0), maxLag);
  const shift = Math.abs(lag) > 1 ? lag : 0;

  const out: Float32Array[] = [];
  for (let c = 0; c < ch; c++) {
    const src = rendered.getChannelData(c);
    const o = new Float32Array(n);
    for (let i = 0; i < n; i++) {
      const j = i + shift;
      o[i] = j >= 0 && j < src.length ? src[j] : 0;
    }
    out.push(o);
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
