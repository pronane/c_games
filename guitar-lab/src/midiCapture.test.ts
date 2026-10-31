import { test } from "node:test";
import assert from "node:assert/strict";
import { MidiCapture, midiFile } from "./midiCapture";
test("note-on velocity zero is note-off and MIDI channels stay distinct", () => {
  const c = new MidiCapture();
  c.message([0x90, 60, 100], 0);
  c.message([0x91, 60, 80], 0.1);
  c.message([0x90, 60, 0], 0.5);
  const notes = c.finish(1);
  assert.equal(notes.length, 2);
  assert.equal(notes[0].duration, 0.5);
  assert.equal(notes[1].channel, 1);
  assert.equal(notes[1].duration, 0.9);
});
test("sustain holds released notes and pedal release ends them", () => {
  const c = new MidiCapture();
  c.message([0xb0, 64, 127], 0);
  c.message([0x90, 60, 80], 0.1);
  c.message([0x80, 60, 0], 0.5);
  assert.equal(c.notes.length, 0);
  c.message([0xb0, 64, 0], 1);
  assert.equal(c.finish(2)[0].duration, 0.9);
});
test("restrikes and all-notes-off finalise pending notes without hanging", () => {
  const c = new MidiCapture();
  c.message([0xb0, 64, 127], 0);
  c.message([0x90, 60, 80], 0);
  c.message([0x80, 60, 0], 0.2);
  c.message([0x90, 60, 90], 0.4);
  c.message([0xb0, 123, 0], 0.8);
  assert.deepEqual(
    c.finish(1).map((n) => n.duration),
    [0.4, 0.4],
  );
});
test("MIDI export has valid header, explicit tempo and track length", () => {
  const bytes = midiFile([
    { midi: 60, channel: 0, velocity: 100, time: 0, duration: 1 },
  ]);
  const v = new DataView(bytes.buffer);
  assert.equal(new TextDecoder().decode(bytes.slice(0, 4)), "MThd");
  assert.equal(v.getUint16(12), 480);
  assert.equal(new TextDecoder().decode(bytes.slice(14, 18)), "MTrk");
  assert.equal(v.getUint32(18), bytes.length - 22);
  assert.deepEqual([...bytes.slice(-4)], [0, 255, 47, 0]);
  assert.ok(bytes.includes(0x90));
});
test("truncated and non-note MIDI messages are ignored", () => {
  const c = new MidiCapture();
  c.message([0x90, 60], 0);
  c.message([0xf8], 0);
  c.message([0xe0, 1, 2], 0);
  assert.equal(c.finish(1).length, 0);
});
