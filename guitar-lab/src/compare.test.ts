import { test } from "node:test";
import assert from "node:assert/strict";
import { barLines, markClass, noteChips, rememberTake, scoreCards, tempoNote, worstLines, type Comparison } from "./compare";

const comparison: Comparison = {
  transcription: "clean-guitar Basic Pitch",
  reports: [
    {
      source: "stem",
      label: "Guitar stem",
      summary: { pitch_accuracy: 0.917, timing_accuracy: 1, completeness: 1, overall: 96, speed_ratio: 1 },
      notes: [],
      bars: [],
      worst_bars: [],
    },
    {
      source: "notation",
      label: "Written notation",
      summary: { pitch_accuracy: 0.917, timing_accuracy: 1, completeness: 1, overall: 96, speed_ratio: 0.67 },
      notes: [
        { id: 0, kind: "correct", bar: 12, beat: 1, message: "", target_midi: 67, target_fret: 3, take_midi: 67 },
        {
          id: 1,
          kind: "wrong_pitch",
          bar: 12,
          beat: 3,
          message: "bar 12 beat 3: played E4, expected F4",
          target_midi: 65,
          target_fret: 1,
          take_midi: 64,
        },
        { id: 2, kind: "missing", bar: 12, beat: 4, message: "bar 12 beat 4: missed B4", target_midi: 71, target_fret: 7, take_midi: null },
        { id: 3, kind: "extra", bar: 12, beat: 4, message: "bar 12 beat 4: extra D3", target_midi: null, take_midi: 50 },
      ],
      bars: [
        { bar: 11, score: 100, messages: [] },
        {
          bar: 12,
          score: 40,
          messages: ["bar 12 beat 3: played E4, expected F4", "bar 12 beat 4: missed B4", "bar 12 beat 4: extra D3"],
        },
      ],
      worst_bars: [
        {
          bar: 12,
          score: 40,
          messages: ["bar 12 beat 3: played E4, expected F4", "bar 12 beat 4: missed B4", "bar 12 beat 4: extra D3"],
        },
      ],
    },
  ],
  combined: {
    pitch_accuracy: 0.917,
    timing_accuracy: 1,
    completeness: 1,
    overall: 96,
    detail: "Average of the guitar-stem notes and the written notation.",
  },
};

test("score cards list stem, notation, and the combined score", () => {
  const cards = scoreCards(comparison);
  assert.deepEqual(cards.map((c) => c.key), ["stem", "notation", "combined"]);
  assert.equal(cards[2].overall, "96%");
  assert.equal(cards[2].label, "Combined");
  assert.match(cards[1].detail, /Pitch 92% · timing 100% · completeness 100%/);
});

test("note chips color wrong, missing, and extra notes and keep the plain-language title", () => {
  const chips = noteChips(comparison.reports[1]);
  assert.equal(chips[1].className, "diff-note diff-wrong-pitch");
  assert.equal(chips[1].title, "bar 12 beat 3: played E4, expected F4");
  assert.equal(chips[1].text, "1");
  assert.equal(chips[1].pitch, "E4");
  assert.equal(markClass("missing"), "diff-note diff-missing");
  assert.equal(chips[2].className, markClass("missing"));
  assert.equal(chips[2].text, "7");
  assert.equal(chips[3].text, "D3");
  assert.equal(chips[0].title, "Matches the target");
});

test("bar feedback names the worst bar and a clean bar", () => {
  const lines = barLines(comparison.reports[1]);
  assert.equal(lines[0].className, "good");
  assert.deepEqual(lines[0].messages, ["All the notes in this bar match."]);
  assert.equal(lines[1].className, "poor");
  assert.equal(lines[1].score, "40%");
  assert.deepEqual(worstLines(comparison.reports[1]), [
    "bar 12 beat 3: played E4, expected F4",
    "bar 12 beat 4: missed B4",
    "bar 12 beat 4: extra D3",
  ]);
});

test("a slower tempo is explained and not treated as a mistake list", () => {
  assert.match(tempoNote(comparison.reports[1]) ?? "", /67% of the target tempo/);
  assert.equal(tempoNote(comparison.reports[0]), null);
});

test("take history keeps the last five", () => {
  let history: string[] = [];
  for (const id of ["a", "b", "c", "d", "e", "f"]) history = rememberTake(history, id);
  assert.deepEqual(history, ["b", "c", "d", "e", "f"]);
});
