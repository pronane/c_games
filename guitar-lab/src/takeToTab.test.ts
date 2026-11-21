import { test } from "node:test";
import assert from "node:assert/strict";
import { onGrid, stringLabels, tabText } from "./takeToTab";

const STD = [64, 59, 55, 50, 45, 40]; // string 1 (high e) first, as the instrument profile gives it

test("notes move so bar 1 starts at 0", () => {
  const out = onGrid(
    [
      { time: 0.2, duration: 0.3, midi: 40 },
      { time: 0.96, duration: 0.3, midi: 43 },
      { time: 1.5, duration: 0.3, midi: 45 },
    ],
    1,
  );
  assert.deepEqual(out.map((n) => n.time), [0, 0.5]);
});

test("string labels, high e first", () => {
  assert.deepEqual(stringLabels(STD), ["e", "B", "G", "D", "A", "E"]);
  assert.deepEqual(stringLabels([64, 59, 55, 50, 45, 38]), ["E", "B", "G", "D", "A", "D"]);
});

test("text tab on a 16th grid", () => {
  // 120 BPM: a quarter note is 0.5 s. Low E open on beat 1, fret 3 on beat 2, an E chord shape (two strings) on beat 3,
  // and fret 12 on the high e on beat 1 of bar 2.
  const tab = tabText(
    [
      { time: 0, duration: 0.5, midi: 40, string: 6, fret: 0 },
      { time: 0.5, duration: 0.5, midi: 43, string: 6, fret: 3 },
      { time: 1.0, duration: 0.5, midi: 52, string: 4, fret: 2 },
      { time: 1.01, duration: 0.5, midi: 47, string: 5, fret: 2 },
      { time: 2.0, duration: 0.5, midi: 76, string: 1, fret: 12 },
      { time: 2.5, duration: 0.5, midi: 30 },
    ],
    120,
    STD,
  );
  const rows = tab.trimEnd().split("\n");
  assert.equal(rows.length, 6);
  assert.ok(rows[5].startsWith("E|0-------3-------"), rows[5]);
  assert.ok(rows[3].startsWith("D|----------------2-"), rows[3]);
  assert.ok(rows[4].startsWith("A|----------------2-"), rows[4]);
  // Bar 2 starts after the first bar line; the two-digit fret widens its column on every string.
  const bar2 = rows.map((r) => r.split("|")[2]);
  assert.ok(bar2[0].startsWith("12-"), bar2[0]);
  assert.ok(bar2[5].startsWith("---"), bar2[5]);
  assert.equal(new Set(rows.map((r) => r.length)).size, 1, "all strings the same length");
});

test("nothing fretted, no tab", () => {
  assert.equal(tabText([{ time: 0, duration: 1, midi: 30 }], 100, STD), "");
});
