import test from 'node:test';
import assert from 'node:assert/strict';
import { packetDigest, validateListeningPacket, validateLabels, listeningResult, type ListeningPacket } from './listeningReview';
async function packet() {
  const p: ListeningPacket = { schema: 'fretwork-listening-packet-v1', id: 'anonymous-packet', window: { start: 10, end: 12, speed: 1 }, reference: { notes: [{ time: 0, duration: .5, midi: 64 }], bpm: 120, tuning: 'standard', part: 'lead', revision: 1, reviewed: true }, audio: 'data:audio/wav;base64,' + btoa('RIFF' + '\0'.repeat(4) + 'WAVE' + '\0'.repeat(32)), sha256: '' };
  p.sha256 = await packetDigest(p); return p;
}
test('packet whitelist excludes predictions and private project history', async () => {
  const p = await packet(); assert.deepEqual(await validateListeningPacket(p), p);
  await assert.rejects(validateListeningPacket({ ...p, predictions: ['wrong note'] }));
  await assert.rejects(validateListeningPacket({ ...p, reference: { ...p.reference, summary: 100 } }));
});
test('checksum binds reference notes, time mapping and audio', async () => {
  const p = await packet();
  await assert.rejects(validateListeningPacket({ ...p, window: { ...p.window, start: 9 } }), /checksum mismatch/i);
  await assert.rejects(validateListeningPacket({ ...p, reference: { ...p.reference, notes: [{ time: 0, duration: .5, midi: 65 }] } }), /checksum mismatch/i);
  await assert.rejects(validateListeningPacket({ ...p, audio: 'data:audio/wav;base64,' + btoa('RIFF' + '1'.repeat(4) + 'WAVE' + '1'.repeat(32)) }), /checksum mismatch/i);
});
test('malformed and out-of-bounds listening packets are rejected', async () => {
  const p = await packet();
  for (const bad of [null, {}, { ...p, window: { ...p.window, speed: 0 } }, { ...p, reference: { ...p.reference, notes: [{ time: 3, duration: .5, midi: 64 }] } }, { ...p, audio: 'data:text/html;base64,eA==' }]) await assert.rejects(validateListeningPacket(bad));
});
test('review results require declared exposure, bind packet and never self-certify ground truth', async () => {
  const p = await packet(); const labels = [{ start: .2, end: .5, kind: 'pitch' as const, comment: 'audible semitone difference' }];
  assert.ok(validateLabels(labels, 2)); assert.equal(validateLabels([{ ...labels[0], end: 3 }], 2), false);
  assert.throws(() => listeningResult(p, '', 'no', labels, true));
  assert.throws(() => listeningResult(p, 'teacher-a', '', labels, true));
  const result = listeningResult(p, 'teacher-a', 'no', labels, true);
  assert.equal(result.packet_sha256, p.sha256); assert.equal(result.independent_ground_truth, false);
  assert.equal(result.seen_app_predictions, 'no');
});
