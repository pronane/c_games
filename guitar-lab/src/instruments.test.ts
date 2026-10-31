import { test } from "node:test";
import assert from "node:assert/strict";
import {
  defaultSettings,
  resolveInstrument,
  tabPosition,
  instruments,
} from "./instruments";
test("profiles specify range, stem, method, notation and feedback policy", () => {
  for (const p of instruments) {
    assert.ok(p.midi_min < p.midi_max);
    assert.ok(p.separation_stem);
    assert.equal(p.transcription_method, "basic_pitch_onnx");
    assert.ok(p.notations.includes(p.default_notation));
    assert.ok(p.feedback.includes("timing_candidates"));
  }
});
test("drop D and capo affect actual tab and pitch bounds", () => {
  const p = resolveInstrument({
    ...defaultSettings(),
    tuning: "drop_d",
    capo: 2,
  });
  assert.equal(p.openStrings[5], 40);
  assert.equal(p.midi_min, 40);
  assert.deepEqual(tabPosition(40, p), { string: 6, fret: 0 });
  assert.equal(p.maxFret, 22);
  assert.equal(tabPosition(39, p), undefined);
});
test("bass has four strings and E1; piano has no tab", () => {
  const bass = resolveInstrument(defaultSettings("bass"));
  assert.equal(bass.midi_min, 28);
  assert.equal(bass.openStrings.length, 4);
  assert.deepEqual(tabPosition(28, bass), { string: 4, fret: 0 });
  const piano = resolveInstrument(defaultSettings("piano"));
  assert.equal(piano.midi_min, 21);
  assert.equal(piano.midi_max, 108);
  assert.equal(piano.openStrings.length, 0);
  assert.equal(piano.settings.notation, "notes");
  assert.equal(tabPosition(60, piano), undefined);
});
test("invalid combinations fail rather than silently changing instrument settings", () => {
  assert.throws(
    () => resolveInstrument({ ...defaultSettings("bass"), capo: 1 }),
    /capo/,
  );
  assert.throws(
    () => resolveInstrument({ ...defaultSettings(), tuning: "unknown" }),
    /tuning/,
  );
  assert.throws(
    () =>
      resolveInstrument({ ...defaultSettings("piano"), notation: "tablature" }),
    /notation/,
  );
});
