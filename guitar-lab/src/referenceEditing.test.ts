import test from 'node:test';
import assert from 'node:assert/strict';
import { chordSelection, copyNotes, edit, noteLabel, redo, snapTime, transformNotes, undo, validNotes, type EditHistory } from './referenceEditing';
const notes = [{ time: 1, duration: .5, midi: 60 }, { time: 1.02, duration: .4, midi: 64 }, { time: 2, duration: 1, midi: 67 }];
test('chord selection groups near-simultaneous attacks, not next notes', () => {
  assert.deepEqual(chordSelection(notes, 0), [0, 1]); assert.deepEqual(chordSelection(notes, 2), [2]);
});
test('group pitch and time transforms preserve intervals and do not mutate source', () => {
  const before = copyNotes(notes), moved = transformNotes(notes, [0, 1], 4, { time: .5, pitch: 2 });
  assert.deepEqual(notes, before); assert.equal(moved[1].midi - moved[0].midi, 4);
  assert.equal(moved[0].time, 1.5); assert.equal(moved[1].time, 1.52); assert.deepEqual(moved[2], notes[2]);
});
test('selection stays within pitch, time and duration boundaries as a group', () => {
  assert.equal(transformNotes(notes, [0, 1], 4, { time: -9 })[0].time, 0);
  const high = transformNotes(notes, [0, 1], 4, { pitch: 1000 }); assert.equal(high[1].midi, 127); assert.equal(high[0].midi, 123);
  assert.equal(transformNotes(notes, [0, 1], 4, { length: -100 })[1].duration, .01);
  assert.ok(validNotes(transformNotes(notes, [0, 1, 2], 4, { length: 100 }), 4));
  assert.ok(validNotes(transformNotes(notes, [0, 1, 2], 4, { time: 100 }), 4));
});
test('snap supports no snap, half beats and nearest sixteenth', () => {
  assert.equal(snapTime(1.12, 0), 1.12); assert.equal(snapTime(1.12, .125), 1.125); assert.equal(noteLabel(64), 'E4');
});
test('undo and redo restore complete drafts, diverging edits clear redo', () => {
  let h: EditHistory = { past: [], present: copyNotes(notes), future: [] };
  h = edit(h, transformNotes(h.present, [0], 4, { pitch: 1 }));
  assert.equal(h.present[0].midi, 61); h = undo(h); assert.deepEqual(h.present, notes);
  h = redo(h); assert.equal(h.present[0].midi, 61);
  h = undo(h); h = edit(h, notes.slice(0, 1)); assert.equal(h.future.length, 0);
  assert.equal(redo(h), h);
});
test('draft history is bounded and rejects impossible data through validator', () => {
  let h: EditHistory = { past: [], present: [], future: [] };
  for (let i = 0; i < 100; i++) h = edit(h, [{ time: 0, duration: .5, midi: i }]);
  assert.equal(h.past.length, 40);
  for (const bad of [{ time: -1, duration: .5, midi: 60 }, { time: 0, duration: NaN, midi: 60 }, { time: 0, duration: .5, midi: 60.5 }, { time: 3.9, duration: .5, midi: 60 }]) assert.equal(validNotes([bad], 4), false);
});
