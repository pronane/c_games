import { extract, chord, compare } from "./analysis";
self.onmessage = (
  event: MessageEvent<{ a: Float32Array; b: Float32Array; duration: number }>,
) => {
  try {
    const { a, b, duration } = event.data,
      reference = extract(a, 16000),
      take = extract(b, 16000);
    if (reference.rms < 0.008 || take.rms < 0.008)
      throw Error(
        "One recording is too quiet to analyse. Check the input level.",
      );
    const chords = [];
    for (let t = 0; t < duration; t += 2)
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
