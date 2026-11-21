import { test } from "node:test";
import assert from "node:assert/strict";
import { chordAt, songChords, takeOnSong } from "./followAlong";
import { place } from "./Fretboard";

const chords = [
  { chord: "N", start: 0, end: 1 },
  { chord: "G", start: 1, end: 3 },
  { chord: "G", start: 3, end: 4 },
  { chord: "C", start: 4, end: 5 },
  { chord: "D", start: 5, end: 9 },
];

test("current and next chord", () => {
  assert.equal(chordAt(chords, 2).now?.chord, "G");
  assert.equal(chordAt(chords, 2).next?.chord, "C");
  assert.equal(chordAt(chords, 0.5).now, null);
  assert.equal(chordAt(chords, 0.5).next?.chord, "G");
  assert.equal(chordAt(chords, 6).next, null);
});

test("song chords, most played first", () => {
  assert.deepEqual(songChords(chords), ["D", "G", "C"]);
});

test("take notes land on the song clock", () => {
  const notes = takeOnSong(
    [
      { take_time: 2, take_midi: 64, target_midi: 64, target_string: 2, target_fret: 5 },
      { take_time: 3, take_midi: 65, target_midi: 64, target_string: 2, target_fret: 5 },
      { take_time: null, take_midi: null, target_midi: 60 },
    ],
    10,
    0.5,
  );
  assert.equal(notes.length, 2);
  assert.equal(notes[0].time, 11);
  assert.equal(notes[0].fret, 5);
  assert.equal(notes[1].fret, null);
});

test("notes are placed on the tab's string, else the lowest fret", () => {
  const std = [64, 59, 55, 50, 45, 40]; // string 1 (high e) first, as the profile gives it
  assert.deepEqual(place({ time: 0, duration: 1, midi: 64, string: 2, fret: 5 }, std, 22), { string: 2, fret: 5 });
  assert.deepEqual(place({ time: 0, duration: 1, midi: 64 }, std, 22), { string: 1, fret: 0 });
  assert.deepEqual(place({ time: 0, duration: 1, midi: 41 }, std, 22), { string: 6, fret: 1 });
  assert.equal(place({ time: 0, duration: 1, midi: 30 }, std, 22), null);
});
