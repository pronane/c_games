import { test } from "node:test";
import assert from "node:assert/strict";
import { chordShape, parseChord, shapeNotes } from "./chordShapes";

const pcs = (name: string) => new Set(shapeNotes(chordShape(name)!).map((m) => m % 12));

test("chord names parse", () => {
  assert.deepEqual(parseChord("F#m7"), { root: 6, quality: "m7" });
  assert.deepEqual(parseChord("Bb"), { root: 10, quality: "" });
  assert.equal(parseChord("N"), null);
});

test("open shapes where they are common", () => {
  assert.deepEqual(chordShape("E")!.frets, [0, 2, 2, 1, 0, 0]);
  assert.deepEqual(chordShape("Am")!.frets, [null, 0, 2, 2, 1, 0]);
  assert.deepEqual(chordShape("C")!.frets, [null, 3, 2, 0, 1, 0]);
});

test("barre shapes sound the right notes", () => {
  const want: Record<string, number[]> = { F: [5, 9, 0], Bm: [11, 2, 6], "C#m": [1, 4, 8], Bb7: [10, 2, 5, 8], Ebmaj7: [3, 7, 10, 2] };
  for (const [name, notes] of Object.entries(want)) assert.deepEqual(pcs(name), new Set(notes), name);
  assert.equal(chordShape("F")!.barre, 1);
  assert.equal(chordShape("Bm")!.barre, 2);
});

test("every root and common quality has a shape with its root and third", () => {
  for (const root of ["C", "C#", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"])
    for (const q of ["", "m", "7", "m7", "sus4", "5"]) {
      const s = chordShape(root + q);
      assert.ok(s, root + q);
      assert.ok(pcs(root + q).has(parseChord(root + q)!.root), root + q);
    }
});

test("diminished and augmented shapes", () => {
  assert.deepEqual(pcs("Bdim"), new Set([11, 2, 5]));
  assert.deepEqual(pcs("Caug"), new Set([0, 4, 8]));
});
