import { test } from "node:test";
import assert from "node:assert/strict";
import { detectPitch, tuningReading } from "./tuner";
function tone(hz: number) {
  return Float32Array.from(
    { length: 8192 },
    (_, i) => 0.2 * Math.sin((2 * Math.PI * hz * i) / 48000),
  );
}
test("tuner detects guitar E2, bass E1 and detuned A4", () => {
  for (const hz of [82.4069, 41.2034, 442]) {
    const p = detectPitch(tone(hz), 48000);
    assert.ok(p);
    assert.ok(
      Math.abs(1200 * Math.log2(p.hz / hz)) < 5,
      `${hz}Hz -> ${p.hz}Hz`,
    );
  }
});
test("tuner rejects silence and unpitched random noise", () => {
  assert.equal(detectPitch(new Float32Array(8192), 48000), null);
  let seed = 5;
  const noise = Float32Array.from({ length: 8192 }, () => {
    seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0;
    return seed / 2 ** 32 - 0.5;
  });
  assert.equal(detectPitch(noise, 48000), null);
});
test("cents and target reflect explicit string or chromatic mode", () => {
  const r = tuningReading(442, [], 69);
  assert.equal(r.target, 69);
  assert.ok(r.cents > 7 && r.cents < 9);
  assert.equal(tuningReading(41.2034, [43, 38, 33, 28]).target, 28);
  assert.equal(tuningReading(440, []).target, 69);
});
