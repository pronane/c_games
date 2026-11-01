import { test } from "node:test";
import assert from "node:assert/strict";
import {
  estimateOffset,
  gainAt,
  loopRange,
  mixInto,
  muteSchedule,
  type BarRole,
} from "./songAudio";
import { tuningReading } from "./tuner";

function plucks(rate: number, seconds: number, times: number[], shift = 0) {
  const out = new Float32Array(Math.round(rate * seconds));
  for (const t of times)
    for (let j = 0; j < rate * 0.3; j++) {
      const k = Math.round((t + shift) * rate) + j;
      if (k >= 0 && k < out.length)
        out[k] += 0.3 * Math.exp((-j / rate) * 12) * Math.sin((2 * Math.PI * 196 * j) / rate);
    }
  return out;
}

test("offset estimation finds a late take (recording latency)", () => {
  const rate = 16000,
    times = [0.2, 0.55, 0.9, 1.4, 1.6, 2.3, 2.8, 3.1, 3.7];
  const ref = plucks(rate, 4, times),
    take = plucks(rate, 4, times, 0.07);
  const offset = estimateOffset(ref, take, rate);
  assert.ok(offset);
  assert.ok(Math.abs(offset.seconds - 0.07) <= 0.011, String(offset.seconds));
});

test("offset estimation abstains on silence", () => {
  const rate = 16000;
  assert.equal(
    estimateOffset(plucks(rate, 4, [0.5, 1, 2]), new Float32Array(rate * 4), rate),
    null,
  );
});

test("lead-only muting silences lead bars and keeps rhythm bars", () => {
  const roles: BarRole[] = [
    { bar: 1, start: 0, end: 2, role: "rhythm" },
    { bar: 2, start: 2, end: 4, role: "lead" },
    { bar: 3, start: 4, end: 6, role: "lead" },
    { bar: 4, start: 6, end: 8, role: "rhythm" },
  ];
  const s = muteSchedule(roles, ["lead"]);
  assert.equal(gainAt(s, 1), 1);
  assert.equal(gainAt(s, 3), 0);
  assert.equal(gainAt(s, 5), 0);
  assert.equal(gainAt(s, 7), 1);
  assert.equal(muteSchedule(roles, []).length, 1);
});

test("loop range follows the bar grid", () => {
  assert.deepEqual(loopRange([0, 2.4, 4.8, 7.2], 2, 3, 10), { start: 2.4, end: 7.2 });
  assert.deepEqual(loopRange([0, 2.4], 2, 5, 3), { start: 2.4, end: 3 });
});

test("mixing places a take at an offset", () => {
  const out: [Float32Array, Float32Array] = [new Float32Array(10), new Float32Array(10)];
  mixInto(out, [Float32Array.from([1, 1, 1])], 0.5, 2);
  assert.deepEqual([...out[0]], [0, 0, 0.5, 0.5, 0.5, 0, 0, 0, 0, 0]);
  assert.deepEqual([...out[1]], [...out[0]]);
});

test("tuner reference follows a recording that is 30 cents sharp", () => {
  const a4 = 440 * 2 ** (30 / 1200);
  const r = tuningReading(a4 * 2 ** ((40 - 69) / 12), [64, 59, 55, 50, 45, 40], null, 30);
  assert.equal(r.target, 40);
  assert.ok(Math.abs(r.cents) < 0.01);
});

// Three guitars, as on many rock records: rhythm left all through, a lead on the right in
// bars 2-3 and a second lead in the centre in bar 5 (bleed of it on the right).
import { buildTargets, targetSchedule, targetBars, timeStretch, barRanges, applySchedule, type PartInfo } from "./songAudio";
const bar = (n: number, role: BarRole["role"], bleed = false): BarRole => ({ bar: n, start: (n - 1) * 2, end: n * 2, role, ...(bleed ? { bleed } : {}) });
const band: PartInfo[] = [
  { id: "guitar_left", label: "Guitar (left)", role: "rhythm", roles: [1, 2, 3, 4, 5].map((n) => bar(n, "rhythm")) },
  { id: "guitar_right", label: "Guitar (right)", role: "lead", roles: [bar(1, "rest", true), bar(2, "lead"), bar(3, "lead"), bar(4, "rest"), bar(5, "rest", true)] },
  { id: "guitar_centre", label: "Guitar (centre)", role: "lead", roles: [bar(1, "rest"), bar(2, "rest", true), bar(3, "rest", true), bar(4, "rest"), bar(5, "lead")] },
];

test("targets offer each guitar, every lead passage and all guitars", () => {
  const targets = buildTargets(band, "Guitar");
  assert.deepEqual(
    targets.map((t) => t.id),
    ["guitar_left", "guitar_right", "guitar_centre", "all:lead", "all"],
  );
  const allLead = targets.find((t) => t.id === "all:lead")!;
  assert.deepEqual(allLead.parts, ["guitar_right", "guitar_centre"]);
  assert.equal(allLead.detail, "bars 2–3, 5");
  assert.deepEqual([...targetBars(allLead, band)].sort(), [2, 3, 5]);
  assert.equal(barRanges([11, 5, 6, 7, 12, 8, 14]), "5–8, 11–12, 14");
});

test("a guitar that plays lead and rhythm can be taken over in either role", () => {
  const both: PartInfo = { id: "g", label: "Guitar", role: "lead and rhythm", roles: [bar(1, "rhythm"), bar(2, "lead"), bar(3, "rhythm")] };
  const ids = buildTargets([both], "Guitar").map((t) => [t.id, t.label, t.detail]);
  assert.deepEqual(ids, [
    ["g", "The guitar part", "lead and rhythm"],
    ["g:lead", "Guitar · lead bars", "bars 2"],
    ["g:rhythm", "Guitar · rhythm bars", "bars 1, 3"],
  ]);
});

test("taking over every lead mutes each lead in its bars and the bleed copies too", () => {
  const allLead = buildTargets(band, "Guitar").find((t) => t.id === "all:lead")!;
  const gain = (part: PartInfo, mode: "without" | "only", t: number) => {
    const s = targetSchedule(allLead, part, band, mode);
    return s ? gainAt(s, t) : 1;
  };
  const [left, right, centre] = band;
  // Backing track: rhythm untouched; right lead silent in bars 2-3 and its bleed bar 5.
  assert.equal(gain(left, "without", 3), 1);
  assert.equal(gain(right, "without", 3), 0);
  assert.equal(gain(right, "without", 9), 0);
  assert.equal(gain(right, "without", 7), 1);
  // Centre: lead in bar 5 silent; its bleed of the right lead (bars 2-3) also silent.
  assert.equal(gain(centre, "without", 9), 0);
  assert.equal(gain(centre, "without", 5), 0);
  assert.equal(gain(centre, "without", 1), 1);
  // Guide / reference: only the lead bars of the lead parts.
  assert.equal(gain(left, "only", 3), 0);
  assert.equal(gain(right, "only", 3), 1);
  assert.equal(gain(right, "only", 7), 0);
  assert.equal(gain(centre, "only", 9), 1);
});

test("whole-part target silences that part only", () => {
  const right = buildTargets(band, "Guitar").find((t) => t.id === "guitar_right")!;
  assert.deepEqual(targetSchedule(right, band[1], band, "without"), [{ time: 0, gain: 0 }]);
  assert.equal(targetSchedule(right, band[0], band, "without"), null);
  const applied = applySchedule([new Float32Array(400).fill(1)], 100, [{ time: 0, gain: 1 }, { time: 1.97, gain: 1 }, { time: 2, gain: 0 }]);
  assert.equal(applied[0][100], 1);
  assert.equal(applied[0][300], 0);
});

test("slowing down keeps the pitch and stretches the length", () => {
  const rate = 16000,
    seconds = 2,
    hz = 220,
    x = new Float32Array(rate * seconds);
  for (let i = 0; i < x.length; i++) x[i] = 0.5 * Math.sin((2 * Math.PI * hz * i) / rate);
  const [y] = timeStretch([x], rate, 0.7);
  assert.ok(Math.abs(y.length - x.length / 0.7) < 2);
  // Count rising zero crossings in the steady middle.
  let crossings = 0;
  const a = Math.round(y.length * 0.2),
    b = Math.round(y.length * 0.8);
  for (let i = a + 1; i < b; i++) if (y[i - 1] < 0 && y[i] >= 0) crossings++;
  const measured = crossings / ((b - a) / rate);
  assert.ok(Math.abs(measured - hz) < 3, `pitch ${measured} Hz`);
  // No dropouts: level stays steady.
  let rms = 0;
  for (let i = a; i < b; i++) rms += y[i] * y[i];
  assert.ok(Math.abs(Math.sqrt(rms / (b - a)) - 0.5 / Math.SQRT2) < 0.05);
});
