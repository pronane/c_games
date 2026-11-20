import { test } from "node:test";
import assert from "node:assert/strict";
import { addEntry, DEFAULT_TRAINER, nextSpeed, songKey, summarise, trainerDone, type ProgressEntry } from "./progress";

const e = (at: number, from: number, to: number, speed: number, score: number | null): ProgressEntry => ({
  at,
  from,
  to,
  speed,
  score,
  against: "tab: Lead",
});

test("song key ignores the file extension and case", () => {
  assert.equal(songKey("Every Rose.MP3", 255.4), songKey("every rose.wav", 255.2));
});

test("history keeps the newest entries", () => {
  let h: ProgressEntry[] = [];
  for (let i = 0; i < 5; i++) h = addEntry(h, e(i, 1, 4, 1, i), 3);
  assert.deepEqual(h.map((x) => x.at), [2, 3, 4]);
});

test("summary per bar range: best, best at full speed, fastest clean speed", () => {
  const s = summarise([e(1, 3, 6, 0.6, 90), e(2, 3, 6, 0.7, 70), e(3, 3, 6, 1, 60), e(4, 9, 12, 0.8, null)]);
  assert.equal(s.length, 2);
  assert.equal(s[0].from, 9);
  const r = s[1];
  assert.deepEqual([r.takes, r.best, r.bestFull, r.fastestPass], [4 - 1, 90, 60, 0.6]);
  assert.deepEqual(r.scores, [90, 70, 60]);
});

test("speed trainer steps up after a pass, holds after a miss, stops at the top", () => {
  const t = { ...DEFAULT_TRAINER, on: true };
  assert.equal(nextSpeed(t, 0.6, 90), 0.65);
  assert.equal(nextSpeed(t, 0.6, 70), 0.6);
  assert.equal(nextSpeed(t, 0.6, null), 0.6);
  assert.equal(nextSpeed(t, 0.98, 95), 1);
  assert.equal(trainerDone(t, 1, 88), true);
  assert.equal(trainerDone(t, 0.95, 99), false);
});
