import { test } from "node:test";
import assert from "node:assert/strict";
import { summarise, sections } from "./feedback";

const bars = [1, 2, 3, 4].map((n, i) => ({ number: n, time: i * 2 }));
const ok = (t: number, d = 0.01) => ({ kind: "matched", reference_time: t, take_time: t, latency_compensated_seconds: d });

test("summary names the bar and kind of each mistake, worst first", () => {
  const findings = [
    ...[0.1, 0.5, 1, 1.5].map((t) => ok(t)),
    { kind: "pitch_difference", reference_time: 2.5, take_time: 2.5 },
    { kind: "pitch_difference", reference_time: 3, take_time: 3 },
    ok(2.1),
    ok(3.5),
    { kind: "unmatched_reference", reference_time: 4.6 },
    ...[4.1, 5, 5.5].map((t) => ok(t)),
    ...[6.1, 6.6, 7.1, 7.6].map((t) => ({ kind: "timing_difference", reference_time: t, take_time: t - 0.12, latency_compensated_seconds: -0.12 })),
  ];
  const s = summarise(findings, 8, bars);
  assert.deepEqual(s.points, ["rushed bar 4 (about 120 ms early)", "2 wrong notes in bar 2", "1 missed note in bar 3"]);
  assert.deepEqual(s.sections.map((r) => r.score), [100, 50, 75, 50]);
  assert.equal(s.overall, 69);
  assert.match(s.next, /Loop bar (2|4) slowly/);
});

test("a clean take says so and suggests moving on", () => {
  const s = summarise([0.2, 0.9, 2.2, 3.1].map((t) => ok(t)), 4, bars.slice(0, 2));
  assert.deepEqual(s.points, []);
  assert.equal(s.overall, 100);
  assert.match(s.next, /Every note we could compare lined up/);
});

test("extra notes count against the section; no bars falls back to 4-second slices", () => {
  const s = summarise([ok(1), ok(2), { kind: "unmatched_take", take_time: 2.5 }], 6);
  assert.deepEqual(s.sections.map((r) => r.label), ["0–4 s", "4–6 s"]);
  assert.equal(s.sections[0].score, 67);
  assert.equal(s.sections[1].score, null);
  assert.deepEqual(s.points, ["1 extra note in 0–4 s"]);
  assert.equal(sections(8.02, bars).length, 4);
});
