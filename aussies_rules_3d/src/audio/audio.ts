/**
 * Fully synthesized match audio (WebAudio): crowd bed, whistle, kick thuds,
 * bounces, siren and goal roars. No audio files needed — works offline.
 */
export class MatchAudio {
  private ctx: AudioContext | null = null;
  private master: GainNode | null = null;
  private crowdGain: GainNode | null = null;
  private crowdFilter: BiquadFilterNode | null = null;
  private excitement = 0;
  enabled = true;

  init(): void {
    if (this.ctx) return;
    const Ctor =
      typeof window !== 'undefined'
        ? window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext
        : undefined;
    if (!Ctor) return;
    this.ctx = new Ctor();
    this.master = this.ctx.createGain();
    this.master.gain.value = 0.65;
    this.master.connect(this.ctx.destination);
    this.startCrowd();
  }

  resume(): void {
    this.ctx?.resume().catch(() => undefined);
  }

  setEnabled(on: boolean): void {
    this.enabled = on;
    if (this.master) this.master.gain.value = on ? 0.65 : 0;
  }

  private startCrowd(): void {
    if (!this.ctx || !this.master) return;
    const ctx = this.ctx;
    // pink-ish noise loop
    const len = ctx.sampleRate * 3;
    const buffer = ctx.createBuffer(1, len, ctx.sampleRate);
    const data = buffer.getChannelData(0);
    let b0 = 0, b1 = 0, b2 = 0;
    for (let i = 0; i < len; i++) {
      const white = Math.random() * 2 - 1;
      b0 = 0.99765 * b0 + white * 0.099046;
      b1 = 0.963 * b1 + white * 0.2965164;
      b2 = 0.57555 * b2 + white * 1.0526913;
      data[i] = (b0 + b1 + b2 + white * 0.1848) * 0.055;
    }
    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.loop = true;
    this.crowdFilter = ctx.createBiquadFilter();
    this.crowdFilter.type = 'bandpass';
    this.crowdFilter.frequency.value = 620;
    this.crowdFilter.Q.value = 0.6;
    this.crowdGain = ctx.createGain();
    this.crowdGain.gain.value = 0.35;
    src.connect(this.crowdFilter).connect(this.crowdGain).connect(this.master);
    src.start();
  }

  /** Raise crowd excitement (goal, mark, tackle). */
  cheer(amount: number): void {
    this.excitement = Math.min(1, this.excitement + amount);
    if (this.crowdGain && this.ctx) {
      const t = this.ctx.currentTime;
      this.crowdGain.gain.cancelScheduledValues(t);
      this.crowdGain.gain.setTargetAtTime(0.35 + this.excitement * 0.8, t, 0.15);
      this.crowdFilter?.frequency.setTargetAtTime(560 + this.excitement * 420, t, 0.4);
    }
  }

  settle(dt: number): void {
    this.excitement = Math.max(0, this.excitement - dt * 0.12);
    if (this.crowdGain && this.ctx) {
      this.crowdGain.gain.setTargetAtTime(0.35 + this.excitement * 0.8, this.ctx.currentTime, 0.6);
    }
  }

  whistle(long = false): void {
    if (!this.ctx || !this.master) return;
    const ctx = this.ctx;
    const t = ctx.currentTime;
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.type = 'square';
    osc.frequency.value = 2350;
    const lfo = ctx.createOscillator();
    const lfoGain = ctx.createGain();
    lfo.frequency.value = 26;
    lfoGain.gain.value = 190;
    lfo.connect(lfoGain).connect(osc.frequency);
    const dur = long ? 0.75 : 0.28;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.22, t + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    osc.connect(g).connect(this.master);
    osc.start(t);
    lfo.start(t);
    osc.stop(t + dur + 0.05);
    lfo.stop(t + dur + 0.05);
  }

  kick(power = 1): void {
    if (!this.ctx || !this.master) return;
    const ctx = this.ctx;
    const t = ctx.currentTime;
    // thump
    const osc = ctx.createOscillator();
    const og = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(180 + power * 60, t);
    osc.frequency.exponentialRampToValueAtTime(70, t + 0.12);
    og.gain.setValueAtTime(0.4 * power, t);
    og.gain.exponentialRampToValueAtTime(0.001, t + 0.16);
    osc.connect(og).connect(this.master);
    osc.start(t);
    osc.stop(t + 0.2);
    // leather slap
    const len = ctx.sampleRate * 0.05;
    const buf = ctx.createBuffer(1, len, ctx.sampleRate);
    const d = buf.getChannelData(0);
    for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / len) * 0.5;
    const src = ctx.createBufferSource();
    const ng = ctx.createGain();
    ng.gain.value = 0.28 * power;
    src.buffer = buf;
    src.connect(ng).connect(this.master);
    src.start(t);
  }

  bounce(): void {
    if (!this.ctx || !this.master) return;
    const ctx = this.ctx;
    const t = ctx.currentTime;
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.type = 'triangle';
    osc.frequency.setValueAtTime(320, t);
    osc.frequency.exponentialRampToValueAtTime(120, t + 0.09);
    g.gain.setValueAtTime(0.16, t);
    g.gain.exponentialRampToValueAtTime(0.001, t + 0.1);
    osc.connect(g).connect(this.master);
    osc.start(t);
    osc.stop(t + 0.12);
  }

  siren(long = true): void {
    if (!this.ctx || !this.master) return;
    const ctx = this.ctx;
    const t0 = ctx.currentTime;
    const dur = long ? 2.2 : 1.1;
    for (const freq of [620, 465]) {
      const osc = ctx.createOscillator();
      const g = ctx.createGain();
      osc.type = 'sawtooth';
      osc.frequency.value = freq;
      const vib = ctx.createOscillator();
      const vibG = ctx.createGain();
      vib.frequency.value = 7;
      vibG.gain.value = 26;
      vib.connect(vibG).connect(osc.frequency);
      g.gain.setValueAtTime(0.0001, t0);
      g.gain.exponentialRampToValueAtTime(0.16, t0 + 0.08);
      g.gain.setValueAtTime(0.16, t0 + dur - 0.15);
      g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
      osc.connect(g).connect(this.master);
      osc.start(t0);
      vib.start(t0);
      osc.stop(t0 + dur + 0.05);
      vib.stop(t0 + dur + 0.05);
    }
  }

  goalHorn(): void {
    if (!this.ctx || !this.master) return;
    const ctx = this.ctx;
    const t = ctx.currentTime;
    for (const freq of [196, 294]) {
      const osc = ctx.createOscillator();
      const g = ctx.createGain();
      osc.type = 'sawtooth';
      osc.frequency.value = freq;
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(0.12, t + 0.06);
      g.gain.exponentialRampToValueAtTime(0.0001, t + 1.4);
      osc.connect(g).connect(this.master);
      osc.start(t);
      osc.stop(t + 1.5);
    }
    this.cheer(1);
    this.whistle(false);
  }
}
