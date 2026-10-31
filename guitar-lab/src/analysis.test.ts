import { test } from "node:test";
import assert from "node:assert/strict";
import { extract, chord, compare, fingering, note } from "./analysis";
test("silence yields no invented notes or chord", () => {
  const f = extract(new Float32Array(16000), 16000);
  assert.equal(f.events.length, 0);
  assert.equal(chord(f.chroma).name, "Unclear");
});
test("detects a sustained A3", () => {
  const x = Float32Array.from(
    { length: 16000 },
    (_, i) => 0.3 * Math.sin((2 * Math.PI * 220 * i) / 16000),
  );
  const f = extract(x, 16000);
  assert.ok(f.events.some((e) => e.midi === 57));
  assert.equal(note(57), "A3");
});
test("identical features match and silence has unavailable timing", () => {
  const f = extract(new Float32Array(8000), 16000);
  assert.equal(compare(f, f).error, null);
  assert.deepEqual(fingering(40), { string: 6, fret: 0 });
});
