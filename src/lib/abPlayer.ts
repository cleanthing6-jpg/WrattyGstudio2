/**
 * abPlayer.ts -- framework-free A/B controller for "Raw Stems" vs "Mixed Preview".
 */
export type Side = "raw" | "mixed";
export type Phase = "idle" | "loading" | "ready" | "playing" | "paused" | "error";

export interface SideDiag {
  url: string;
  readyState: number;
  networkState: number;
  errorCode: number | null;
  errorName: string | null;
  loadedMs: number | null;
}

export interface State {
  phase: Phase;
  active: Side;
  mode: "sync" | "swap";
  time: number;
  duration: number;
  message: string | null;
  failedSide: Side | null;
  raw: SideDiag;
  mixed: SideDiag;
}

const ERR_NAMES = ["", "MEDIA_ERR_ABORTED", "MEDIA_ERR_NETWORK", "MEDIA_ERR_DECODE", "MEDIA_ERR_SRC_NOT_SUPPORTED"];
const SIDES: Side[] = ["raw", "mixed"];
const LABEL: Record<Side, string> = { raw: "Raw Stems", mixed: "Mixed Preview" };

export interface Options {
  raw: HTMLAudioElement;
  mixed: HTMLAudioElement;
  onChange: (s: State) => void;
  readyTimeoutMs?: number;
  driftToleranceS?: number;
  syncEveryMs?: number;
}

export class ABPlayer {
  private els: Record<Side, HTMLAudioElement>;
  private urls: Record<Side, string> = { raw: "", mixed: "" };
  private ready: Record<Side, boolean> = { raw: false, mixed: false };
  private errors: Record<Side, { code: number; name: string } | null> = { raw: null, mixed: null };
  private loadedAt: Record<Side, number | null> = { raw: null, mixed: null };
  private listeners: Array<[HTMLAudioElement, string, EventListener]> = [];
  private timeout: ReturnType<typeof setTimeout> | null = null;
  private tick: ReturnType<typeof setInterval> | null = null;
  private t0 = 0;
  private dead = false;
  private userPaused = true;
  private st: State;
  private readonly o: Required<Omit<Options, "raw" | "mixed" | "onChange">> & Pick<Options, "onChange">;

  constructor(opts: Options) {
    this.els = { raw: opts.raw, mixed: opts.mixed };
    this.o = {
      onChange: opts.onChange,
      readyTimeoutMs: opts.readyTimeoutMs ?? 10000,
      driftToleranceS: opts.driftToleranceS ?? 0.04,
      syncEveryMs: opts.syncEveryMs ?? 200,
    };
    this.st = {
      phase: "idle", active: "mixed", mode: "sync", time: 0, duration: 0, message: null, failedSide: null,
      raw: this.diagOf("raw"), mixed: this.diagOf("mixed"),
    };
  }

  load(rawUrl: string, mixedUrl: string): void {
    this.t0 = Date.now();
    this.urls = { raw: (rawUrl || "").trim(), mixed: (mixedUrl || "").trim() };
    for (const s of SIDES) {
      if (!this.urls[s]) {
        return this.fail(s, `${LABEL[s]}: no URL was passed to the player. The API response has no ${s === "raw" ? "raw_url" : "mixed preview URL"} (check result.raw_url in /api/mix-preview).`);
      }
      if (!/^(https?:)?\/\//i.test(this.urls[s]) && !this.urls[s].startsWith("/")) {
        return this.fail(s, `${LABEL[s]}: "${this.urls[s].slice(0, 60)}" is not a playable URL.`);
      }
    }
    this.set({ phase: "loading", message: null, failedSide: null });
    for (const s of SIDES) {
      const el = this.els[s];
      this.on(el, "canplay", () => this.markReady(s));
      this.on(el, "loadeddata", () => this.markReady(s));
      this.on(el, "error", () => this.markError(s));
      this.on(el, "timeupdate", () => this.emitTime());
      this.on(el, "ended", () => { this.userPaused = true; this.set({ phase: "paused" }); });
      this.on(el, "pause", () => this.onUnexpectedPause(s));
      el.preload = "auto";
      el.muted = s !== this.st.active;
      el.src = this.urls[s];
      el.load();
    }
    this.timeout = setTimeout(() => this.onTimeout(), this.o.readyTimeoutMs);
  }

  private markReady(s: Side) {
    if (this.dead || this.ready[s]) return;
    this.ready[s] = true;
    this.loadedAt[s] = Date.now() - this.t0;
    if (this.ready.raw && this.ready.mixed) {
      if (this.timeout) clearTimeout(this.timeout);
      const d = Math.min(this.els.raw.duration || 0, this.els.mixed.duration || 0);
      this.set({ phase: this.st.phase === "playing" ? "playing" : "ready", duration: isFinite(d) ? d : 0 });
    } else {
      this.set({});
    }
  }

  private markError(s: Side) {
    if (this.dead) return;
    const e = this.els[s].error;
    const code = e ? e.code : 0;
    this.errors[s] = { code, name: ERR_NAMES[code] || "UNKNOWN" };
    const hint =
      code === 4 ? "the file was not found or is not a format this browser can play (404 / wrong content type)" :
      code === 2 ? "the network request failed" :
      code === 3 ? "the file could not be decoded" : "playback was aborted";
    this.fail(s, `${LABEL[s]} failed: ${this.errors[s]!.name} - ${hint}.`);
  }

  private onTimeout() {
    if (this.dead) return;
    const pending = SIDES.filter((s) => !this.ready[s]);
    if (!pending.length) return;
    const s = pending[0];
    const el = this.els[s];
    const why =
      el.networkState === 3 ? "the browser found no usable source (usually a 404, or the server sent a type it cannot play)" :
      el.networkState === 2 && el.readyState === 0 ? "the request is still pending: the file server is not answering" :
      "it never reported enough data to start";
    this.fail(s, `${LABEL[s]} did not become playable within ${Math.round(this.o.readyTimeoutMs / 1000)} s: ${why}. (networkState ${el.networkState}, readyState ${el.readyState})`);
  }

  async play(): Promise<void> {
    if (this.dead || this.st.phase === "error") return;
    if (!(this.ready.raw && this.ready.mixed)) {
      this.set({ message: "Still loading both previews..." });
      return;
    }
    this.userPaused = false;
    const a = this.st.active, b: Side = a === "raw" ? "mixed" : "raw";
    this.applyAudible();
    const t = this.els[a].currentTime;
    this.els[b].currentTime = t;
    const playA = this.els[a].play();
    const playB = this.st.mode === "sync" ? this.els[b].play() : Promise.resolve();
    const [ra, rb] = await Promise.allSettled([playA, playB]);
    if (this.dead) return;
    if (ra.status === "rejected") {
      const name = (ra.reason && (ra.reason as { name?: string }).name) || "";
      if (name === "AbortError") return;
      this.userPaused = true;
      return this.fail(a, name === "NotAllowedError"
        ? "The browser blocked playback. Tap Play again."
        : `${LABEL[a]} could not start: ${name || String(ra.reason)}`, false);
    }
    if (rb.status === "rejected") this.enterSwapMode();
    this.startTicker();
    this.set({ phase: "playing", message: null });
  }

  pause(): void {
    this.userPaused = true;
    for (const s of SIDES) this.els[s].pause();
    this.stopTicker();
    if (this.st.phase === "playing") this.set({ phase: "paused" });
  }

  seek(t: number): void {
    for (const s of SIDES) { try { this.els[s].currentTime = t; } catch {} }
    this.emitTime();
  }

  async select(side: Side): Promise<void> {
    if (side === this.st.active) return;
    const from = this.st.active;
    this.set({ active: side });
    if (this.st.mode === "sync") { this.applyAudible(); return; }
    const t = this.els[from].currentTime;
    this.els[side].currentTime = t;
    this.applyAudible();
    if (this.st.phase === "playing") {
      try { await this.els[side].play(); } catch {}
      this.els[from].pause();
    }
  }

  private applyAudible() {
    for (const s of SIDES) {
      const audible = s === this.st.active;
      this.els[s].muted = !audible;
      this.els[s].volume = audible ? 1 : 0;
    }
  }

  private enterSwapMode() {
    const b: Side = this.st.active === "raw" ? "mixed" : "raw";
    try { this.els[b].pause(); } catch {}
    this.set({ mode: "swap" });
  }

  private onUnexpectedPause(s: Side) {
    if (this.dead || this.userPaused || this.st.mode !== "sync") return;
    if (s !== this.st.active && this.st.phase === "playing") this.enterSwapMode();
  }

  private startTicker() {
    this.stopTicker();
    this.tick = setInterval(() => {
      if (this.dead || this.st.mode !== "sync") return;
      const a = this.els[this.st.active], b = this.els[this.st.active === "raw" ? "mixed" : "raw"];
      if (Math.abs(a.currentTime - b.currentTime) > this.o.driftToleranceS) b.currentTime = a.currentTime;
    }, this.o.syncEveryMs);
  }

  private stopTicker() { if (this.tick) { clearInterval(this.tick); this.tick = null; } }

  private emitTime() {
    if (this.dead) return;
    this.set({ time: this.els[this.st.active].currentTime || 0 });
  }

  private fail(side: Side, message: string, stop = true) {
    if (this.timeout && stop) clearTimeout(this.timeout);
    this.set({ phase: "error", message, failedSide: side });
  }

  private diagOf(s: Side): SideDiag {
    const el = this.els[s];
    const e = this.errors[s];
    return { url: this.urls[s], readyState: el.readyState, networkState: el.networkState,
      errorCode: e ? e.code : null, errorName: e ? e.name : null, loadedMs: this.loadedAt[s] };
  }

  private set(patch: Partial<State>) {
    this.st = { ...this.st, ...patch, raw: this.diagOf("raw"), mixed: this.diagOf("mixed") };
    this.o.onChange(this.st);
  }

  private on(el: HTMLAudioElement, evt: string, fn: EventListener) {
    el.addEventListener(evt, fn);
    this.listeners.push([el, evt, fn]);
  }

  getState(): State { return this.st; }

  destroy(): void {
    this.dead = true;
    if (this.timeout) clearTimeout(this.timeout);
    this.stopTicker();
    for (const [el, evt, fn] of this.listeners) el.removeEventListener(evt, fn);
    this.listeners = [];
    for (const s of SIDES) { const el = this.els[s]; try { el.pause(); el.removeAttribute("src"); el.load(); } catch {} }
  }
}
