export type MidiNote = {
  midi: number;
  channel: number;
  velocity: number;
  time: number;
  duration: number;
};
type Active = { midi: number; channel: number; velocity: number; time: number };
export class MidiCapture {
  notes: MidiNote[] = [];
  private held = new Map<string, Active>();
  private sustained = new Map<string, Active>();
  private pedal = new Set<number>();
  private close(key: string, end: number, source: Map<string, Active>) {
    const n = source.get(key);
    if (n) {
      this.notes.push({ ...n, duration: Math.max(0.001, end - n.time) });
      source.delete(key);
    }
  }
  message(data: Uint8Array | number[], time: number) {
    if (data.length < 2 || this.notes.length >= 10000) return;
    const status = data[0] & 0xf0,
      channel = data[0] & 15,
      pitch = data[1],
      value = data[2] ?? 0,
      key = `${channel}:${pitch}`,
      t = Math.max(0, time);
    if ((status === 0x90 || status === 0x80) && data.length < 3) return;
    if (status === 0x90 && value > 0) {
      this.close(key, t, this.held);
      this.close(key, t, this.sustained);
      this.held.set(key, { midi: pitch, channel, velocity: value, time: t });
    } else if (status === 0x80 || (status === 0x90 && value === 0)) {
      if (this.pedal.has(channel)) {
        const n = this.held.get(key);
        if (n) {
          this.close(key, t, this.sustained);
          this.sustained.set(key, n);
          this.held.delete(key);
        }
      } else this.close(key, t, this.held);
    } else if (status === 0xb0 && data.length >= 3 && pitch === 64) {
      if (value >= 64) this.pedal.add(channel);
      else {
        this.pedal.delete(channel);
        for (const [k, n] of this.sustained)
          if (n.channel === channel) this.close(k, t, this.sustained);
      }
    } else if (status === 0xb0 && (pitch === 120 || pitch === 123)) {
      for (const pool of [this.held, this.sustained])
        for (const [k, n] of pool)
          if (n.channel === channel) this.close(k, t, pool);
      this.pedal.delete(channel);
    }
  }
  finish(time: number) {
    for (const pool of [this.held, this.sustained])
      for (const k of pool.keys()) this.close(k, time, pool);
    this.pedal.clear();
    return this.notes.sort((a, b) => a.time - b.time || a.midi - b.midi);
  }
}
function vlq(n: number) {
  const bytes = [n & 127];
  while ((n >>>= 7) > 0) bytes.unshift((n & 127) | 128);
  return bytes;
}
export function midiFile(notes: MidiNote[]): Uint8Array {
  // Format 0, 480 PPQ, explicit 120 BPM. Each second is 960 ticks.
  const events = notes
    .flatMap((n) => [
      {
        tick: Math.round(n.time * 960),
        off: false,
        bytes: [0x90 | n.channel, n.midi, n.velocity],
      },
      {
        tick: Math.round((n.time + n.duration) * 960),
        off: true,
        bytes: [0x80 | n.channel, n.midi, 0],
      },
    ])
    .sort((a, b) => a.tick - b.tick || Number(b.off) - Number(a.off));
  const track = [0, 0xff, 0x51, 3, 7, 0xa1, 0x20];
  let last = 0;
  for (const e of events) {
    track.push(...vlq(Math.max(0, e.tick - last)), ...e.bytes);
    last = e.tick;
  }
  track.push(0, 0xff, 0x2f, 0);
  const len = track.length;
  return new Uint8Array([
    0x4d,
    0x54,
    0x68,
    0x64,
    0,
    0,
    0,
    6,
    0,
    0,
    0,
    1,
    1,
    0xe0,
    0x4d,
    0x54,
    0x72,
    0x6b,
    (len >>> 24) & 255,
    (len >>> 16) & 255,
    (len >>> 8) & 255,
    len & 255,
    ...track,
  ]);
}
