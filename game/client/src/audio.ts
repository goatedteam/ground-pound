// Sound and music. Files and loop points come from assets/audio/manifest.json, written by
// game/tools/prepare_audio.py. Everything is decoded into Web Audio buffers so short sounds
// fire without delay and the music loops on exact sample positions.
//
// The context is created while the game loads so the base song can start on the loading
// screen. Most browsers keep it suspended until the player taps, clicks or presses a key;
// the loading screen asks for that tap, and the song starts then.

interface SfxDef { files: string[]; gain?: number }
interface MusicDef { file: string; loopStart: number; loopEnd: number; gain?: number }
interface Manifest { sfx: Record<string, SfxDef>; music: Record<string, MusicDef> }

const BASE = './assets/audio/';
const XFADE = 0.9; // seconds between music tracks
const CROWD_UNDER_SONG = 0.16; // arena murmur kept low under the base song
const CROWD_ALONE = 0.3; // murmur level when no base song is installed

class AudioEngine {
  private ctx: AudioContext | null = null;
  private master: GainNode | null = null;
  private sfxBus: GainNode | null = null;
  private musicBus: GainNode | null = null;
  private manifest: Manifest | null = null;
  private ext = '.mp3';
  private buffers = new Map<string, Promise<AudioBuffer | null>>();
  private lastTake = new Map<string, number>();
  private loops = new Map<string, { src: AudioBufferSourceNode; gain: GainNode }>();
  private track: { name: string; src: AudioBufferSourceNode; gain: GainNode } | null = null;
  private crowd: { src: AudioBufferSourceNode; gain: GainNode } | null = null;
  private wanted: 'base' | 'fight' | null = null;
  private on = true;

  get enabled() { return this.on; }

  async load() {
    try {
      this.manifest = await fetch(BASE + 'manifest.json').then(r => (r.ok ? r.json() : null));
    } catch { this.manifest = null; }
    const probe = document.createElement('audio');
    this.ext = probe.canPlayType('audio/webm; codecs="opus"') ? '.webm' : '.mp3';
    this.start();
    const unlock = () => this.start();
    for (const ev of ['pointerdown', 'keydown', 'touchend']) window.addEventListener(ev, unlock, { passive: true });
  }

  /** Call from inside a tap or key handler so a sound played in that handler is heard. */
  unlock() { this.start(); }

  /** True once the browser lets sound play. */
  get running() { return this.ctx?.state === 'running'; }

  private start() {
    if (!this.manifest) return;
    if (!this.ctx) {
      const Ctx = window.AudioContext || (window as any).webkitAudioContext;
      if (!Ctx) return;
      this.ctx = new Ctx();
      this.master = this.ctx.createGain();
      this.master.gain.value = this.on ? 1 : 0;
      this.master.connect(this.ctx.destination);
      this.sfxBus = this.ctx.createGain(); this.sfxBus.gain.value = 0.9; this.sfxBus.connect(this.master);
      this.musicBus = this.ctx.createGain(); this.musicBus.gain.value = 0.55; this.musicBus.connect(this.master);
      // decode everything while the loading screen is up so the first spin is not silent
      for (const def of Object.values(this.manifest.sfx)) def.files.forEach(f => this.buffer(f));
      for (const def of Object.values(this.manifest.music)) this.buffer(def.file);
    }
    if (this.ctx.state === 'suspended') this.ctx.resume().catch(() => {});
    if (this.wanted && this.track?.name !== this.wanted) this.music(this.wanted);
  }

  private buffer(file: string): Promise<AudioBuffer | null> {
    let p = this.buffers.get(file);
    if (!p) {
      p = fetch(BASE + file + this.ext)
        .then(r => (r.ok ? r.arrayBuffer() : Promise.reject(r.status)))
        .then(b => this.ctx!.decodeAudioData(b))
        .catch(() => null);
      this.buffers.set(file, p);
    }
    return p;
  }

  private pick(name: string): string | null {
    const def = this.manifest?.sfx[name];
    if (!def || !def.files.length) return null;
    if (def.files.length === 1) return def.files[0];
    const last = this.lastTake.get(name) ?? -1;
    let i = Math.floor(Math.random() * def.files.length); // presentation variety only, never an outcome
    if (i === last) i = (i + 1) % def.files.length;
    this.lastTake.set(name, i);
    return def.files[i];
  }

  /** Fire a one-shot sound. intensity raises pitch and level a little (used for chained hits). */
  play(name: string, opts: { intensity?: number; gain?: number } = {}) {
    if (!this.ctx || !this.on) return;
    const file = this.pick(name);
    if (!file) return;
    const def = this.manifest!.sfx[name];
    const k = Math.min(Math.max((opts.intensity ?? 1) - 1, 0), 6);
    this.buffer(file).then(buf => {
      if (!buf || !this.ctx) return;
      const src = this.ctx.createBufferSource();
      src.buffer = buf;
      src.playbackRate.value = 1 + k * 0.035;
      const g = this.ctx.createGain();
      g.gain.value = (def.gain ?? 1) * (opts.gain ?? 1) * (1 + k * 0.06);
      src.connect(g).connect(this.sfxBus!);
      src.start();
    });
  }

  /** Start a looping sound (the win count-up); stopLoop ends it. */
  loop(name: string) {
    if (!this.ctx || !this.on || this.loops.has(name)) return;
    const file = this.pick(name);
    if (!file) return;
    this.buffer(file).then(buf => {
      if (!buf || !this.ctx || this.loops.has(name)) return;
      const src = this.ctx.createBufferSource();
      src.buffer = buf; src.loop = true;
      const g = this.ctx.createGain(); g.gain.value = this.manifest!.sfx[name].gain ?? 1;
      src.connect(g).connect(this.sfxBus!);
      src.start();
      this.loops.set(name, { src, gain: g });
    });
  }

  stopLoop(name: string) {
    const l = this.loops.get(name);
    if (!l || !this.ctx) return;
    this.loops.delete(name);
    l.gain.gain.setTargetAtTime(0, this.ctx.currentTime, 0.03);
    l.src.stop(this.ctx.currentTime + 0.2);
  }

  /** Switch the music. The base game has its song with a low arena murmur under it; the Title Fight has its own song. */
  music(name: 'base' | 'fight' | null) {
    this.wanted = name;
    if (!this.ctx || !this.manifest) return;
    const now = this.ctx.currentTime;
    if (this.track && this.track.name !== name) {
      this.fadeOut(this.track, now);
      this.track = null;
    }
    const def = name ? this.manifest.music[name] : undefined;
    if (name === 'base') this.crowdBed(def ? CROWD_UNDER_SONG : CROWD_ALONE);
    else if (this.crowd) { this.fadeOut(this.crowd, now); this.crowd = null; }
    if (def && !this.track) this.bed(name!, def.file, def.gain ?? 1, def.loopStart, def.loopEnd);
  }

  private fadeOut(l: { src: AudioBufferSourceNode; gain: GainNode }, now: number) {
    l.gain.gain.cancelScheduledValues(now);
    l.gain.gain.setValueAtTime(l.gain.gain.value, now);
    l.gain.gain.linearRampToValueAtTime(0, now + XFADE);
    try { l.src.stop(now + XFADE + 0.05); } catch { /* never started: still decoding */ }
  }

  private crowdBed(level: number) {
    const def = this.manifest?.sfx.crowd_bed;
    if (!def || this.crowd || !this.ctx) return;
    const file = this.pick('crowd_bed');
    if (!file) return;
    const pending = this.ctx.createGain(); // claims the slot while the buffer decodes
    this.crowd = { src: this.ctx.createBufferSource(), gain: pending };
    const slot = this.crowd;
    this.buffer(file).then(buf => {
      if (!buf || !this.ctx || this.crowd !== slot) return;
      const src = this.ctx.createBufferSource();
      src.buffer = buf; src.loop = true;
      const t = this.ctx.currentTime;
      pending.gain.setValueAtTime(0, t);
      pending.gain.linearRampToValueAtTime(level * (def.gain ?? 1), t + XFADE);
      src.connect(pending).connect(this.musicBus!);
      src.start();
      slot.src = src;
    });
  }

  private bed(name: 'base' | 'fight', file: string, gain: number, loopStart: number, loopEnd: number) {
    this.buffer(file).then(buf => {
      if (!buf || !this.ctx || this.wanted !== name || this.track) return;
      const src = this.ctx.createBufferSource();
      src.buffer = buf; src.loop = true;
      if (loopEnd > loopStart) { src.loopStart = loopStart; src.loopEnd = Math.min(loopEnd, buf.duration); }
      const g = this.ctx.createGain();
      const t = this.ctx.currentTime;
      g.gain.setValueAtTime(0, t);
      g.gain.linearRampToValueAtTime(gain, t + XFADE);
      src.connect(g).connect(this.musicBus!);
      src.start();
      this.track = { name, src, gain: g };
    });
  }

  setEnabled(on: boolean) {
    this.on = on;
    if (this.master && this.ctx) this.master.gain.setTargetAtTime(on ? 1 : 0, this.ctx.currentTime, 0.05);
    if (!on) [...this.loops.keys()].forEach(k => this.stopLoop(k));
  }
}

export const audio = new AudioEngine();
