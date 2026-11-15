import test from 'node:test';
import assert from 'node:assert/strict';
import { recordingQuality, qualityMessage, validateQuality } from './recordingQuality';
test('silence and empty capture are no-signal, not a successful take', () => {
  assert.equal(recordingQuality([new Float32Array(100)], 100).status, 'no_signal');
  assert.equal(recordingQuality([new Float32Array()], 100).status, 'no_signal');
});
test('quiet capture and digital-ceiling capture are cautions, not confirmed playing errors', () => {
  const low = recordingQuality([new Float32Array(100).fill(.001)], 100);
  assert.equal(low.status, 'low_level'); assert.ok(Math.abs(low.rmsDb + 60) < .001);
  const clipped = recordingQuality([new Float32Array(100).fill(1)], 100);
  assert.equal(clipped.status, 'ceiling'); assert.equal(clipped.clippedFraction, 1);
  assert.match(qualityMessage(clipped), /Intentional distortion/);
});
test('healthy-looking signal still does not prove accuracy', () => {
  const q = recordingQuality([Float32Array.from({ length: 1000 }, (_, i) => .2 * Math.sin(i))], 1000);
  assert.equal(q.status, 'usable'); assert.equal(q.seconds, 1); assert.ok(validateQuality(q));
  assert.match(qualityMessage(q), /does not verify/);
  assert.equal(validateQuality({ ...q, rmsDb: NaN }), false);
});
test('nonfinite samples and invalid rates fail explicitly', () => {
  assert.throws(() => recordingQuality([Float32Array.of(NaN)], 100));
  assert.throws(() => recordingQuality([Float32Array.of(0)], 0));
});
