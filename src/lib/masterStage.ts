// One universal adaptive master stage.
// Measures the mix, then adapts tone, glue, mono bass,
// level and peak control for each song.

const dbToLin = (db: number) => Math.pow(10, db / 20);
const linToDb = (x: number) => 20 * Math.log10(Math.max(x, 1e-12));
const clamp = (v: number, a: number, b: number) => {
  return Math.min(b, Math.max(a, v));
};

function makeBuffer(sr: number, len: number): AudioBuffer {
  const ctx = new OfflineAudioContext(2, 1, sr);
  return ctx.createBuffer(2, len, sr);
}

// K weighted (approx BS.1770)
async function kWeight(buf: AudioBuffer) {
  const sr = buf.sampleRate;
  const chn = buf.numberOfChannels;
  const ctx = new OfflineAudioContext(chn, buf.length, sr);
  const src = ctx.createBufferSource();
  src.buffer = buf;
  const hs = ctx.createBiquadFilter();
  hs.type = "highshelf";
  hs.frequency.value = 1681;
  hs.gain.value = 4;
  hs.Q.value = 0.7071;
  const hp = ctx.createBiquadFilter();
  hp.type = "highpass";
  hp.frequency.value = 38;
  hp.Q.value = 0.5;
  src.connect(hs);
  hs.connect(hp);
  hp.connect(ctx.destination);
  src.start(0);
  const out = await ctx.startRendering();
  const ch: Float32Array[] = [];
  for (let c = 0; c < out.numberOfChannels; c++) {
    ch.push(out.getChannelData(c));
  }
  return ch;
}

function lufs(ch: Float32Array[], sr: number): number {
  const block = Math.round(sr * 0.4);
  const hop = Math.round(block / 4);
  const n = ch[0].length;
  const ms: number[] = [];
  for (let s = 0; s + block <= n; s += hop) {
    let sum = 0;
    for (let c = 0; c < ch.length; c++) {
      const d = ch[c];
      for (let i = s; i < s + block; i++) {
        sum += d[i] * d[i];
      }
    }
    ms.push(sum / block);
  }
  if (ms.length === 0) return -70;
  const loud = ms.map((m) => {
    return -0.691 + 10 * Math.log10(Math.max(m, 1e-12));
  });
  const abs: number[] = [];
  for (let i = 0; i < ms.length; i++) {
    if (loud[i] > -70) abs.push(ms[i]);
  }
  if (abs.length === 0) return -70;
  let mAbs = 0;
  for (const v of abs) mAbs += v;
  mAbs /= abs.length;
  const gate = -0.691 + 10 * Math.log10(Math.max(mAbs, 1e-12));
  const rel = gate - 10;
  const kept: number[] = [];
  for (let i = 0; i < ms.length; i++) {
    if (loud[i] > -70 && loud[i] > rel) kept.push(ms[i]);
  }
  const use = kept.length > 0 ? kept : abs;
  let m = 0;
  for (const v of use) m += v;
  m /= use.length;
  return -0.691 + 10 * Math.log10(Math.max(m, 1e-12));
}
function samplePeak(ch: Float32Array[]): number {
  let p = 0;
  for (const d of ch) {
    for (let i = 0; i < d.length; i++) {
      const a = Math.abs(d[i]);
      if (a > p) p = a;
    }
  }
  return p;
}

function truePeak(ch: Float32Array[]): number {
  let tp = 0;
  for (const d of ch) {
    for (let i = 0; i < d.length - 1; i++) {
      const a = d[i];
      const b = d[i + 1];
      for (let j = 0; j < 4; j++) {
        const v = Math.abs(a + (b - a) * (j / 4));
        if (v > tp) tp = v;
      }
    }
  }
  return tp;
}

function rmsOf(ch: Float32Array[]): number {
  let s = 0;
  let n = 0;
  for (const d of ch) {
    for (let i = 0; i < d.length; i++) {
      s += d[i] * d[i];
      n++;
    }
  }
  return Math.sqrt(s / Math.max(n, 1));
}

function bandRatios(buf: AudioBuffer) {
  const sr = buf.sampleRate;
  const aLow = 1 - Math.exp(-2 * Math.PI * 120 / sr);
  const a25 = 1 - Math.exp(-2 * Math.PI * 2500 / sr);
  const a55 = 1 - Math.exp(-2 * Math.PI * 5500 / sr);
  let lpL = 0;
  let lp25 = 0;
  let lp55 = 0;
  let pTot = 0;
  let pLow = 0;
  let pHar = 0;
  const n = buf.length;
  for (let c = 0; c < buf.numberOfChannels; c++) {
    const d = buf.getChannelData(c);
    for (let i = 0; i < n; i++) {
      const x = d[i];
      pTot += x * x;
      lpL += (x - lpL) * aLow;
      pLow += lpL * lpL;
      lp25 += (x - lp25) * a25;
      lp55 += (x - lp55) * a55;
      const band = lp25 - lp55;
      pHar += band * band;
    }
  }
  const t = Math.max(pTot, 1e-12);
  return { lowRatio: pLow / t, harshRatio: pHar / t };
}

function correlation(buf: AudioBuffer): number {
  if (buf.numberOfChannels < 2) return 1;
  const L = buf.getChannelData(0);
  const R = buf.getChannelData(1);
  let lr = 0;
  let ll = 0;
  let rr = 0;
  for (let i = 0; i < buf.length; i++) {
    lr += L[i] * R[i];
    ll += L[i] * L[i];
    rr += R[i] * R[i];
  }
  return lr / Math.max(Math.sqrt(ll * rr), 1e-12);
}

async function measure(buf: AudioBuffer) {
  const kch = await kWeight(buf);
  const ch: Float32Array[] = [];
  for (let c = 0; c < buf.numberOfChannels; c++) {
    ch.push(buf.getChannelData(c));
  }
  const rms = rmsOf(ch);
  const pk = samplePeak(ch);
  const bands = bandRatios(buf);
  const l = lufs(kch, buf.sampleRate);
  const lowR = bands.lowRatio;
  const harR = bands.harshRatio;
  return {
    lufs: l,
    crestDb: linToDb(pk) - linToDb(rms),
    lowRatio: lowR,
    harshRatio: harR,
    corr: correlation(buf),
  };
}
async function shape(
  buf: AudioBuffer,
  o: {
    lowShelfDb: number;
    harshCutDb: number;
    glueWet: number;
    glueRatio: number;
    monoBassHz: number;
  }
): Promise<AudioBuffer> {
  const sr = buf.sampleRate;
  const ctx = new OfflineAudioContext(2, buf.length, sr);
  const src = ctx.createBufferSource();
  src.buffer = buf;
  const split = ctx.createChannelSplitter(2);
  const merge = ctx.createChannelMerger(2);
  src.connect(split);

  const lpL = ctx.createBiquadFilter();
  lpL.type = "lowpass";
  lpL.frequency.value = o.monoBassHz;
  lpL.Q.value = 0.7071;
  const lpR = ctx.createBiquadFilter();
  lpR.type = "lowpass";
  lpR.frequency.value = o.monoBassHz;
  lpR.Q.value = 0.7071;
  const hpL = ctx.createBiquadFilter();
  hpL.type = "highpass";
  hpL.frequency.value = o.monoBassHz;
  hpL.Q.value = 0.7071;
  const hpR = ctx.createBiquadFilter();
  hpR.type = "highpass";
  hpR.frequency.value = o.monoBassHz;
  hpR.Q.value = 0.7071;

  const mono = ctx.createGain();
  mono.gain.value = 0.5;

  split.connect(lpL, 0);
  split.connect(lpR, 1);
  lpL.connect(mono);
  lpR.connect(mono);
  mono.connect(merge, 0, 0);
  mono.connect(merge, 0, 1);
  split.connect(hpL, 0);
  split.connect(hpR, 1);
  hpL.connect(merge, 0, 0);
  hpR.connect(merge, 0, 1);

  const lowShelf = ctx.createBiquadFilter();
  lowShelf.type = "lowshelf";
  lowShelf.frequency.value = 100;
  lowShelf.gain.value = o.lowShelfDb;

  const harsh = ctx.createBiquadFilter();
  harsh.type = "peaking";
  harsh.frequency.value = 3500;
  harsh.Q.value = 1.0;
  harsh.gain.value = o.harshCutDb;

  const comp = ctx.createDynamicsCompressor();
  comp.threshold.value = -18;
  comp.knee.value = 6;
  comp.ratio.value = o.glueRatio;
  comp.attack.value = 0.03;
  comp.release.value = 0.2;

  const dry = ctx.createGain();
  const wet = ctx.createGain();
  dry.gain.value = 1 - o.glueWet * 0.5;
  wet.gain.value = o.glueWet;

  merge.connect(lowShelf);
  lowShelf.connect(harsh);
  harsh.connect(dry);
  harsh.connect(comp);
  comp.connect(wet);
  dry.connect(ctx.destination);
  wet.connect(ctx.destination);
  src.start(0);
  return await ctx.startRendering();
}
function applyGain(ch: Float32Array[], g: number) {
  for (const d of ch) {
    for (let i = 0; i < d.length; i++) d[i] *= g;
  }
}

function softClip(ch: Float32Array[], ceilDb: number, kneeDb: number) {
  const ceil = dbToLin(ceilDb);
  const knee = dbToLin(ceilDb - kneeDb);
  const span = Math.max(ceil - knee, 1e-9);
  for (const d of ch) {
    for (let i = 0; i < d.length; i++) {
      const a = Math.abs(d[i]);
      if (a <= knee) continue;
      const over = (a - knee) / span;
      const t = Math.tanh(over);
      const out = knee + t * span;
      d[i] = d[i] < 0 ? -out : out;
    }
  }
}

export async function masterStage(
  buf: AudioBuffer,
  opts?: { targetLUFS?: number; truePeakDb?: number }
): Promise<AudioBuffer> {
  const targetLUFS = opts?.targetLUFS ?? -11;
  const ceilDb = opts?.truePeakDb ?? -1;

  const m = await measure(buf);

  let lowShelfDb = 0;
  if (m.lowRatio < 0.08) lowShelfDb = 1.5;
  else if (m.lowRatio < 0.12) lowShelfDb = 0.75;
  else if (m.lowRatio > 0.24) lowShelfDb = -1.0;

  let harshCutDb = 0;
  if (m.harshRatio > 0.18) harshCutDb = -2.0;
  else if (m.harshRatio > 0.12) harshCutDb = -1.0;

  let glueWet = 0.04;
  if (m.crestDb > 12) glueWet = 0.16;
  else if (m.crestDb > 9) glueWet = 0.10;

  let glueRatio = 1.2;
  if (m.crestDb > 12) glueRatio = 1.8;
  else if (m.crestDb > 9) glueRatio = 1.5;

  const shaped = await shape(buf, {
    lowShelfDb: lowShelfDb,
    harshCutDb: harshCutDb,
    glueWet: glueWet,
    glueRatio: glueRatio,
    monoBassHz: 90,
  });

  const after = await measure(shaped);
  const makeupDb = clamp(targetLUFS - after.lufs, -6, 9);

  const ch: Float32Array[] = [];
  for (let c = 0; c < shaped.numberOfChannels; c++) {
    ch.push(shaped.getChannelData(c));
  }
  applyGain(ch, dbToLin(makeupDb));
  softClip(ch, ceilDb, 3);

  const tpDb = linToDb(truePeak(ch));
  if (tpDb > ceilDb) {
    applyGain(ch, dbToLin(ceilDb - tpDb));
  }

  const out = makeBuffer(shaped.sampleRate, shaped.length);
  for (let c = 0; c < out.numberOfChannels; c++) {
    const i = Math.min(c, ch.length - 1);
    const dst = out.getChannelData(c);
    dst.set(ch[i]);
  }
  return out;
}
