export type Event = {
  time: number;
  midi: number;
  strength: number;
  duration: number;
};
export type Features = {
  events: Event[];
  chroma: number[];
  onsets: number[];
  duration: number;
  rms: number;
};
export const names = [
  "C",
  "C♯",
  "D",
  "D♯",
  "E",
  "F",
  "F♯",
  "G",
  "G♯",
  "A",
  "A♯",
  "B",
];
export function note(midi: number) {
  return names[midi % 12] + (Math.floor(midi / 12) - 1);
}
export function fingering(midi: number) {
  const tuning = [64, 59, 55, 50, 45, 40];
  return tuning
    .map((n, i) => ({ string: i + 1, fret: midi - n }))
    .filter((x) => x.fret >= 0 && x.fret <= 24)
    .sort((a, b) => a.fret - b.fret)[0];
}
// Goertzel narrow-band energy: deliberately lightweight, not a polyphonic transcription model.
export function extract(samples: Float32Array, rate: number): Features {
  const hop = Math.round(rate * 0.08),
    size = Math.min(4096, Math.round(rate * 0.12));
  const events: Event[] = [],
    chroma = Array(12).fill(0),
    onsets: number[] = [];
  let previous = 0,
    total = 0,
    frames = 0;
  for (let start = 0; start + size < samples.length; start += hop) {
    let energy = 0;
    for (let j = 0; j < size; j++) energy += samples[start + j] ** 2;
    const rms = Math.sqrt(energy / size);
    total += rms;
    frames++;
    if (rms > 0.012 && rms > previous * 1.55) onsets.push(start / rate);
    previous = rms;
    if (rms < 0.008) continue;
    const powers: number[] = [];
    for (let midi = 40; midi <= 88; midi++) {
      const freq = 440 * 2 ** ((midi - 69) / 12),
        coeff = 2 * Math.cos((2 * Math.PI * freq) / rate);
      let a = 0,
        b = 0;
      for (let j = 0; j < size; j++) {
        const s =
          samples[start + j] *
            (0.5 - 0.5 * Math.cos((2 * Math.PI * j) / (size - 1))) +
          coeff * a -
          b;
        b = a;
        a = s;
      }
      powers.push(Math.max(0, a * a + b * b - coeff * a * b));
    }
    // Harmonics can dominate: highest spectral bin is only a candidate note.
    const peak = Math.max(...powers),
      idx = powers.indexOf(peak),
      midi = idx + 40;
    powers.forEach((p, i) => {
      chroma[(i + 40) % 12] += p;
    });
    const last = events.at(-1);
    if (
      last &&
      last.midi === midi &&
      start / rate - last.time - last.duration < 0.12
    )
      last.duration += hop / rate;
    else
      events.push({
        time: start / rate,
        midi,
        strength: rms,
        duration: hop / rate,
      });
  }
  const sum = chroma.reduce((a, b) => a + b, 0) || 1;
  return {
    events: events.filter((e) => e.duration >= 0.12),
    chroma: chroma.map((x) => x / sum),
    onsets,
    duration: samples.length / rate,
    rms: total / Math.max(frames, 1),
  };
}
export function chord(chroma: number[]) {
  let best = { name: "Unclear", score: 0 };
  if (chroma.reduce((a, b) => a + b, 0) < 0.01) return best;
  for (let root = 0; root < 12; root++)
    for (const minor of [false, true]) {
      const score = [0, minor ? 3 : 4, 7].reduce(
        (s, i) => s + chroma[(root + i) % 12],
        0,
      );
      if (score > best.score)
        best = { name: names[root] + (minor ? "m" : ""), score };
    }
  return best;
}
export function compare(ref: Features, take: Features) {
  const similarity = ref.chroma.reduce(
    (s, v, i) => s + Math.min(v, take.chroma[i]),
    0,
  );
  const offsets = take.onsets
    .map((t) =>
      ref.onsets.length
        ? ref.onsets.reduce((a, b) =>
            Math.abs(b - t) < Math.abs(a - t) ? b : a,
          ) - t
        : NaN,
    )
    .filter(Number.isFinite);
  const error = offsets.length
    ? offsets.reduce((s, n) => s + Math.abs(n), 0) / offsets.length
    : null;
  return {
    similarity,
    error,
    offset: offsets.length
      ? offsets.reduce((s, n) => s + n, 0) / offsets.length
      : null,
  };
}
