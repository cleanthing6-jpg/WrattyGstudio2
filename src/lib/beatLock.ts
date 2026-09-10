// Beat-Locked mix.
// The beat is NEVER processed. It goes to the mix at unity.
// Only the vocal is processed.

const dbToLin = (db: number) => Math.pow(10, db / 20);

export async function beatLockedMix(
  beat: AudioBuffer,
  vocal: AudioBuffer,
  opts?: { vocalDb?: number }
): Promise<AudioBuffer> {
  const sr = beat.sampleRate;
  const len = Math.max(beat.length, vocal.length);
  const ctx = new OfflineAudioContext(2, len, sr);

  // BEAT: source -> destination. Nothing between. By design.
  const bSrc = ctx.createBufferSource();
  bSrc.buffer = beat;
  bSrc.connect(ctx.destination);

  // VOCAL: full chain only.
  const vSrc = ctx.createBufferSource();
  vSrc.buffer = vocal;

  const trim = ctx.createGain();
  trim.gain.value = 0.7;

  const hp = ctx.createBiquadFilter();
  hp.type = "highpass";
  hp.frequency.value = 70;
  hp.Q.value = 0.7071;

  const mud = ctx.createBiquadFilter();
  mud.type = "peaking";
  mud.frequency.value = 250;
  mud.Q.value = 1.0;
  mud.gain.value = -2;

  const box = ctx.createBiquadFilter();
  box.type = "peaking";
  box.frequency.value = 500;
  box.Q.value = 1.2;
  box.gain.value = -1;

  const comp = ctx.createDynamicsCompressor();
  comp.threshold.value = -24;
  comp.ratio.value = 3;
  comp.attack.value = 0.015;
  comp.release.value = 0.1;
  comp.knee.value = 11;

  const makeup = ctx.createGain();
  makeup.gain.value = dbToLin(3);

  const deess = ctx.createBiquadFilter();
  deess.type = "peaking";
  deess.frequency.value = 7000;
  deess.Q.value = 1.5;
  deess.gain.value = -3;

  const body = ctx.createBiquadFilter();
  body.type = "peaking";
  body.frequency.value = 170;
  body.Q.value = 1.0;
  body.gain.value = 0.5;

  const pres = ctx.createBiquadFilter();
  pres.type = "peaking";
  pres.frequency.value = 2800;
  pres.Q.value = 1.0;
  pres.gain.value = 0.8;

  const air = ctx.createBiquadFilter();
  air.type = "highshelf";
  air.frequency.value = 11000;
  air.gain.value = 0.5;

  const level = ctx.createGain();
  level.gain.value = dbToLin(opts?.vocalDb ?? -6);

  vSrc.connect(trim);
  trim.connect(hp);
  hp.connect(mud);
  mud.connect(box);
  box.connect(comp);
  comp.connect(makeup);
  makeup.connect(deess);
  deess.connect(body);
  body.connect(pres);
  pres.connect(air);
  air.connect(level);
  level.connect(ctx.destination);

  bSrc.start(0);
  vSrc.start(0);
  return await ctx.startRendering();
}

export function gateVocal(
  buf: AudioBuffer,
  floorDb = -42,
  rangeDb = -12
): AudioBuffer {
  const sr = buf.sampleRate;
  const ch = buf.numberOfChannels;
  const n = buf.length;
  const tmp = new OfflineAudioContext(2, 1, sr);
  const out = tmp.createBuffer(2, n, sr);
  const aA = 1 - Math.exp(-1 / (sr * 0.005));
  const aR = 1 - Math.exp(-1 / (sr * 0.120));
  const th = dbToLin(floorDb);
  const min = dbToLin(rangeDb);
  let env = 0;
  for (let i = 0; i < n; i++) {
    let s0 = 0;
    for (let c = 0; c < ch; c++) {
      const v = Math.abs(buf.getChannelData(c)[i]);
      if (v > s0) s0 = v;
    }
    const alpha = s0 > env ? aA : aR;
    env += (s0 - env) * alpha;
    let g = 1;
    if (env < th) g = Math.max(min, env / th);
    for (let c = 0; c < ch; c++) {
      out.getChannelData(c)[i] = buf.getChannelData(c)[i] * g;
    }
  }
  return out;
}
