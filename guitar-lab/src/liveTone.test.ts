import { test } from "node:test";
import assert from "node:assert/strict";
import { driveCurve, isDry, roomImpulse } from "./liveTone";
import { DEFAULT_SOUND } from "./guitarTone";

test("drive curve keeps full scale at full scale and is symmetric", () => {
  const c = driveCurve(12, 0.5, 1025);
  assert.ok(Math.abs((c[c.length - 1]) - (0.5)) < 1e-5);
  assert.ok(Math.abs((c[0]) - (-0.5)) < 1e-5);
  assert.ok(Math.abs((c[512]) - (0)) < 1e-5);
  // High gain squashes quiet input up close to the ceiling (that is the distortion).
  const hot = driveCurve(150, 1, 1025);
  assert.ok((hot[512 + 52]) > (0.99));
});

test("room impulse decays and is the same every time", () => {
  const [a] = roomImpulse(8000, 1),
    [b] = roomImpulse(8000, 1);
  assert.deepEqual(Array.from(a.subarray(0, 50)), Array.from(b.subarray(0, 50)));
  const energy = (x: Float32Array) => x.reduce((s, v) => s + v * v, 0);
  assert.ok((energy(a.subarray(0, 2000))) > (20 * energy(a.subarray(6000, 8000))));
});

test("a clean amp with no pedals leaves the take alone", () => {
  assert.equal(isDry(DEFAULT_SOUND), true);
  assert.equal(isDry({ ...DEFAULT_SOUND, reverb: true }), false);
});

