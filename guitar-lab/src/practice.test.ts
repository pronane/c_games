import { test } from "node:test";
import assert from "node:assert/strict";
import { addClicks, clickTimes, detectHits, summariseLatency } from "./practice";

test("clicks follow the beat grid, accent on beat one, inside the range", () => {
  const beats = Array.from({ length: 12 }, (_, i) => i * 0.5);
  const clicks = clickTimes(beats, 1.0, 4.0);
  assert.deepEqual(clicks.map((c) => c.time), [1, 1.5, 2, 2.5, 3, 3.5]);
  assert.deepEqual(clicks.map((c) => c.accent), [false, false, true, false, false, false]);
});

test("clicks land at stretched positions when slowed down", () => {
  const rate = 8000,
    out = [new Float32Array(rate * 4)];
  addClicks(out, rate, [{ time: 2, accent: true }], 1, 0.5); // 1 s into the song at 50% → 2 s
  const first = out[0].findIndex((v) => Math.abs(v) > 0.01);
  assert.ok(Math.abs(first / rate - 2) < 0.002, `click at ${first / rate}`);
});

function recording(rate: number, seconds: number, hits: number[], noise = 0.002) {
  const x = new Float32Array(rate * seconds);
  let seed = 7;
  for (let i = 0; i < x.length; i++) {
    seed = (seed * 16807) % 2147483647;
    x[i] = noise * (seed / 2147483647 - 0.5);
  }
  for (const t of hits)
    for (let j = 0; j < rate * 0.2; j++) {
      const k = Math.round(t * rate) + j;
      if (k < x.length) x[k] += 0.4 * Math.exp((-j / rate) * 30) * Math.sin((2 * Math.PI * 330 * j) / rate);
    }
  return x;
}

test("speaker loopback: a steady 112 ms delay is measured and trusted", () => {
  const rate = 16000,
    clicks = [0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4];
  const x = recording(rate, 5, clicks.map((t) => t + 0.112));
  const result = summariseLatency(detectHits(x, rate, clicks), "speakers");
  assert.ok(Math.abs(result.ms - 112) <= 2, `${result.ms} ms`);
  assert.equal(result.ok, true);
  assert.equal(result.used, 8);
});

test("play-along: loose human timing still gives the median; silence is rejected", () => {
  const rate = 16000,
    clicks = [0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4],
    jitter = [0.01, -0.015, 0.02, 0, -0.01, 0.012, -0.02, 0.005];
  const x = recording(rate, 5, clicks.map((t, i) => t + 0.09 + jitter[i]));
  const result = summariseLatency(detectHits(x, rate, clicks), "play-along");
  assert.ok(Math.abs(result.ms - 95) <= 8, `${result.ms} ms`);
  assert.equal(result.ok, true);
  const silent = summariseLatency(detectHits(recording(rate, 5, []), rate, clicks), "play-along");
  assert.equal(silent.ok, false);
  assert.equal(silent.used, 0);
});

test("uneven clicks defeat a regular noise that would fake a steady delay", async () => {
  const { jitteredTimes, detectHits, summariseLatency } = await import("./practice");
  const rate = 16000;
  let seed = 7;
  const random = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const clicks = jitteredTimes(0.3, 8, 0.5, random);
  // A device that beeps every 0.5 s on its own, unrelated to the clicks.
  const audio = new Float32Array(rate * 6);
  for (let b = 0.385; b < 6; b += 0.5)
    for (let i = 0; i < 400; i++) audio[Math.round(b * rate) + i] = 0.5 * Math.sin(i * 0.4) * Math.exp(-i / 100);
  const result = summariseLatency(detectHits(audio, rate, clicks), "speakers");
  assert.equal(result.ok, false);
  // Evenly spaced clicks would have been fooled.
  const even = Array.from({ length: 8 }, (_, i) => 0.3 + i * 0.5);
  assert.equal(summariseLatency(detectHits(audio, rate, even), "speakers").ok, true);
});
