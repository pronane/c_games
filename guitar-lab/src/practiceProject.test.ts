import test from 'node:test';
import assert from 'node:assert/strict';
import { newProject, validateProject, phraseNotes, comparable, issueStatus, issueKey, confirmedCount, type PracticeSeed, type Attempt } from './practiceProject';
const seed: PracticeSeed = { title: 'Song', part: 'Rhythm guitar', tuning: 'drop_d', capo: 0, bpm: 120, duration: 30, origin: 'chart', notes: [{ time: 2, duration: 2, midi: 50 }, { time: 3, duration: .5, midi: 57 }] };
test('project starts unverified, snapshots notes and validates', () => {
  const p = newProject(seed); assert.equal(p.trust, 'unverified'); assert.equal(p.attempts.length, 0);
  p.notes[0].midi = 60; assert.equal(seed.notes[0].midi, 50); assert.equal(validateProject(p), p);
});
test('phrase uses half-open time bounds and scales offsets and durations, not pitch', () => {
  const p = newProject(seed); assert.deepEqual(phraseNotes(p, { id: 'x', name: 'chorus', start: 2, end: 3 }, .5), [{ time: 0, duration: 2, midi: 50 }]);
});
test('invalid projects and oversized/malformed references fail closed', () => {
  for (const change of [{ version: 2 }, { duration: Infinity }, { duration: 700 }, { notes: [{ time: -1, duration: .5, midi: 60 }] }, { notes: [{ time: 0, duration: .5, midi: 60.2 }] }, { sections: [] }, { attempts: [{ audio: 'bad' }] }, { notes: [{ time: 0, duration: NaN, midi: 60 }] }, { trust: 'perfect' }]) assert.throws(() => validateProject({ ...newProject(seed), ...change }));
});
const attempt: Attempt = { id: 'a', created: 1, revision: 1, start: 0, end: 20, speed: .7, reviews: {}, latencyMeasured: false };
test('progress compares only exact phrase, speed and reference revision', () => {
  assert.ok(comparable(attempt, { ...attempt, id: 'b' }));
  for (const change of [{ start: 1 }, { end: 21 }, { speed: .8 }, { revision: 2 }]) assert.equal(comparable(attempt, { ...attempt, ...change }), false);
  assert.equal(confirmedCount({ ...attempt, reviews: { a: 'confirmed', b: 'dismissed', c: 'unsure' } }), 1);
});
test('weak evidence, duration, inferred fingering and uncalibrated timing are never confident claims', () => {
  const n = { id: 1, kind: 'late', bar: 2, beat: 1, message: 'late' };
  assert.match(issueStatus(n, 'unverified', true), /Reference/);
  assert.match(issueStatus(n, 'reviewed', false), /delay/);
  assert.match(issueStatus({ ...n, kind: 'uncertain' }, 'reviewed', true), /Uncertain/);
  assert.match(issueStatus({ ...n, kind: 'wrong_duration' }, 'reviewed', true), /Uncertain/);
  assert.match(issueStatus({ ...n, heard_faintly: true }, 'reviewed', true), /Uncertain/);
  assert.equal(issueKey(n), '2:1:late');
});
test('overlapping excluded regions remain excluded for a newly named retry', async () => {
  const { excludedPhrase, exercise } = await import('./practiceProject');
  const p = newProject(seed); p.ignored = [p.sections[0].id];
  assert.ok(excludedPhrase(p, { id: 'new', name: 'retry', start: 5, end: 10 }));
  assert.equal(excludedPhrase(p, { id: 'new', name: 'other', start: 20, end: 22 }), false);
  assert.match(exercise('late'), /click/);
});
