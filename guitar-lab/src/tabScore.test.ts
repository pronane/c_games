import { test } from "node:test";
import assert from "node:assert/strict";
import * as alphaTab from "@coderline/alphatab";
import { scoreToPiece, synthesize, excerpt, matchTuning, pickTrack } from "./tabScore";
import { detectPitch } from "./tuner";

const settings = new alphaTab.Settings();
// alphaTex: fret.string with string 1 = high e. 90 BPM, two bars, a tie, a tempo change to 120.
const tex = `\\title "Test riff" \\tempo 90 .
0.5.4 2.4.4 2.3.8 0.3.8 (0.1 1.2).4 |
\\tempo 120 3.1.2 -.1.4 r.4 |`;

test("Guitar Pro / alphaTex notes become timed tab notes", () => {
  const score = alphaTab.importer.ScoreLoader.loadAlphaTex(tex, settings);
  const piece = scoreToPiece(score, 0);
  assert.equal(piece.title, "Test riff");
  assert.deepEqual(piece.tuning, [64, 59, 55, 50, 45, 40]);
  const q = 60 / 90;
  assert.deepEqual(
    piece.notes.map((n) => [n.midi, n.string, n.fret, +n.time.toFixed(3)]),
    [
      [45, 5, 0, 0],
      [52, 4, 2, +q.toFixed(3)],
      [57, 3, 2, +(2 * q).toFixed(3)],
      [55, 3, 0, +(2.5 * q).toFixed(3)],
      [60, 2, 1, +(3 * q).toFixed(3)],
      [64, 1, 0, +(3 * q).toFixed(3)],
      [67, 1, 3, +(4 * q).toFixed(3)],
    ],
  );
  // Bar 2 is at 120 BPM: the half note tied to a quarter lasts 3 beats of 0.5 s.
  const tied = piece.notes[piece.notes.length - 1];
  assert.ok(Math.abs(tied.duration - 1.5) < 1e-6, String(tied.duration));
  assert.deepEqual(piece.bars.map((b) => +b.time.toFixed(3)), [0, +(4 * q).toFixed(3)]);
  assert.ok(Math.abs(piece.duration - (4 * q + 2)) < 1e-6);
  assert.equal(piece.beats.length, 8);
});

test("Guitar Pro round trip keeps strings and frets", () => {
  const score = alphaTab.importer.ScoreLoader.loadAlphaTex(tex, settings);
  const gp = new alphaTab.exporter.Gp7Exporter().export(score, settings);
  const back = scoreToPiece(alphaTab.importer.ScoreLoader.loadScoreFromBytes(gp, settings), 0);
  assert.deepEqual(
    back.notes.map((n) => [n.midi, n.string, n.fret]),
    scoreToPiece(score, 0).notes.map((n) => [n.midi, n.string, n.fret]),
  );
});

test("tuning match, track choice and excerpts", () => {
  assert.equal(matchTuning([64, 59, 55, 50, 45, 38], { standard: [64, 59, 55, 50, 45, 40], drop_d: [64, 59, 55, 50, 45, 38] }), "drop_d");
  assert.equal(matchTuning([1, 2], { standard: [64] }), null);
  const score = alphaTab.importer.ScoreLoader.loadAlphaTex(tex, settings);
  assert.equal(pickTrack(score, 6), 0);
  const piece = scoreToPiece(score, 0);
  const ex = excerpt(piece, piece.bars[1].time, piece.duration, 0.5);
  assert.equal(ex.notes.length, 1);
  assert.equal(ex.notes[0].time, 0);
  assert.ok(Math.abs(ex.notes[0].duration - 3) < 1e-6); // 1.5 s at half speed
  assert.deepEqual(ex.bars, [{ number: 2, time: 0 }]);
});

test("the app's rendition plays the written pitch, slowed without changing pitch", () => {
  const rate = 44100;
  for (const midi of [40, 57, 64, 76]) {
    const audio = synthesize([{ time: 0, duration: 1, midi }], rate, 1.2, 0.5);
    const hz = 440 * 2 ** ((midi - 69) / 12),
      p = detectPitch(audio.subarray(Math.round(0.2 * rate), Math.round(0.2 * rate) + 4096), rate);
    assert.ok(p, `no pitch for ${midi}`);
    const cents = 1200 * Math.log2(p!.hz / hz);
    assert.ok(Math.abs(cents) < 10, `midi ${midi}: ${p!.hz.toFixed(1)} Hz is ${cents.toFixed(1)} cents off`);
  }
  // At half speed a note written at 1 s starts at 2 s.
  const late = synthesize([{ time: 1, duration: 0.5, midi: 57 }], 8000, 3, 0.5);
  let first = late.findIndex((v) => Math.abs(v) > 1e-3);
  assert.ok(Math.abs(first / 8000 - 2) < 0.01);
});
