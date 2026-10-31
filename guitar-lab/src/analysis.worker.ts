import { extract, chord, compare } from "./analysis";
self.onmessage = (
  event: MessageEvent<{
    a: Float32Array;
    b: Float32Array;
    duration: number;
    midi_min?: number;
    midi_max?: number;
    chords?: boolean;
  }>,
) => {
  try {
    const {
        a,
        b,
        duration,
        midi_min = 40,
        midi_max = 88,
        chords: allowChords = true,
      } = event.data,
      reference = extract(a, 16000, midi_min, midi_max),
      take = extract(b, 16000, midi_min, midi_max);
    if (reference.rms < 0.008 || take.rms < 0.008)
      throw Error(
        "One recording is too quiet to analyse. Check the input level.",
      );
    const chords = [];
    for (let t = 0; allowChords && t < duration; t += 2)
      chords.push({
        time: t,
        name: chord(extract(b.slice(t * 16000, (t + 2) * 16000), 16000).chroma)
          .name,
      });
    self.postMessage({
      reference,
      take,
      match: compare(reference, take),
      chords,
    });
  } catch (e) {
    self.postMessage({ error: e instanceof Error ? e.message : String(e) });
  }
};
