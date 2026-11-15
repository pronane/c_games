// Synthetic PCM and mocked comparison: signal-health gates and independent listening workflow, not accuracy.
import assert from 'node:assert/strict';
import { chromium } from 'playwright-core';
function wav(silent) {
  const rate = 22050, count = rate, b = Buffer.alloc(44 + count * 2);
  b.write('RIFF'); b.writeUInt32LE(b.length - 8, 4); b.write('WAVEfmt ', 8); b.writeUInt32LE(16, 16); b.writeUInt16LE(1, 20); b.writeUInt16LE(1, 22); b.writeUInt32LE(rate, 24); b.writeUInt32LE(rate * 2, 28); b.writeUInt16LE(2, 32); b.writeUInt16LE(16, 34); b.write('data', 36); b.writeUInt32LE(count * 2, 40);
  for (let i = 0; i < count; i++) b.writeInt16LE(silent ? 0 : Math.round(6553 * Math.sin(i * 2 * Math.PI * 440 / rate)), 44 + i * 2);
  return b;
}
async function readDownload(page, trigger) { const wait = page.waitForEvent('download'); await trigger(); const d = await wait, stream = await d.createReadStream(), chunks = []; for await (const c of stream) chunks.push(c); return Buffer.concat(chunks); }
const browser = await chromium.launch({ executablePath: process.env.BROWSER_EXECUTABLE_PATH ?? '/tmp/chromium', args: ['--no-sandbox','--autoplay-policy=no-user-gesture-required','--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream'] });
try {
  const page = await browser.newPage(); const errors = []; page.on('pageerror', e => errors.push(String(e)));
  let inferenceCalls = 0;
  await page.route('**/api/compare', route => { inferenceCalls++; return route.fulfill({ json: { reports: [{ source: 'file', label: 'fixture', summary: { overall: 100, pitch_accuracy: 1, timing_accuracy: 1, completeness: 1 }, notes: [], bars: [], worst_bars: [] }], combined: null } }); });
  await page.goto(process.env.STUDIO_URL ?? 'http://127.0.0.1:5173'); const studio = page.locator('#practice-studio');
  const project = { version: 1, id: 'quality-fixture', title: 'Private title not shared', part: 'Rhythm guitar', tuning: 'standard', capo: 0, bpm: 120, duration: 3, notes: [{ time: .2, duration: .3, midi: 64 }], origin: 'chart', revision: 1, practiceSpeed: 1, activeSection: 'phrase', goal: 'Private goal', trust: 'reviewed', sections: [{ id: 'phrase', name: 'phrase', start: 0, end: 1 }], ignored: [], attempts: [], updated: Date.now() };
  await studio.locator('input[accept=".json"]').setInputFiles({ name: 'fixture.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(project)) });
  await studio.getByText('Imported as an unsaved copy.').waitFor();
  await studio.getByLabel('Keep new take audio', { exact: false }).check();
  await studio.getByText('Upload an earlier phrase recording', { exact: true }).click();
  const upload = studio.getByLabel('Upload phrase take');
  await upload.setInputFiles({ name: 'silence.wav', mimeType: 'audio/wav', buffer: wav(true) });
  await studio.getByText('Take captured without a grade: almost no input signal.', { exact: false }).waitFor();
  assert.equal(inferenceCalls, 0);
  await upload.setInputFiles({ name: 'tone.wav', mimeType: 'audio/wav', buffer: wav(false) });
  await studio.getByText('Review the findings by ear,', { exact: false }).waitFor(); assert.equal(inferenceCalls, 1);
  await studio.getByText('Recording check: No basic level problem detected.', { exact: false }).waitFor();
  await studio.getByText('Check recording input before practising', { exact: true }).click();
  await studio.getByRole('button', { name: 'Check input for 3 seconds' }).click();
  await studio.getByText('RMS ', { exact: false }).last().waitFor();
  await studio.getByText('Listening-only teacher/reviewer packet', { exact: true }).click();
  const packetBytes = await readDownload(page, () => studio.getByRole('button', { name: 'Export listening-only packet' }).click());
  const packet = JSON.parse(packetBytes.toString());
  assert.equal(packet.comparison, undefined); assert.equal(packet.reviews, undefined); assert.equal(packet.title, undefined); assert.equal(packet.goal, undefined);
  assert.match(packet.sha256, /^[0-9a-f]{64}$/);
  const reviewer = await browser.newPage(); reviewer.on('pageerror', e => errors.push(String(e)));
  let apiCalls = 0; reviewer.on('request', r => { if (new URL(r.url()).pathname.startsWith('/api/')) apiCalls++; });
  await reviewer.goto((process.env.STUDIO_URL ?? 'http://127.0.0.1:5173') + '?listening-review');
  await reviewer.getByLabel('Open listening packet').setInputFiles({ name: 'packet.json', mimeType: 'application/json', buffer: packetBytes });
  await reviewer.getByText('Checksum verified.', { exact: false }).waitFor();
  assert.equal(await reviewer.locator('#practice-studio').count(), 0); assert.equal(apiCalls, 0);
  await reviewer.waitForFunction(() => document.querySelector('audio')?.readyState >= 1);
  assert.ok(await reviewer.locator('audio').first().evaluate(a => a.duration >= .99 && a.duration <= 1.01));
  await reviewer.locator('audio').first().evaluate(a => a.play());
  await reviewer.locator('audio').last().evaluate(a => a.play());
  await reviewer.locator('audio').last().evaluate(a => a.pause());
  await reviewer.getByLabel('Reviewer pseudonym').fill('teacher-01');
  await reviewer.getByLabel('Have you seen app predictions', { exact: false }).selectOption('no');
  await reviewer.getByLabel('Observation start seconds').fill('0.1'); await reviewer.getByLabel('Observation end seconds').fill('0.5');
  await reviewer.getByLabel('Observation type').selectOption('uncertain'); await reviewer.getByLabel('Observation comment').fill('Synthetic tone, no real guitar judgement.');
  await reviewer.getByRole('button', { name: 'Add listening observation' }).click();
  await reviewer.getByLabel('I listened through the whole take').check();
  const labelsBytes = await readDownload(reviewer, () => reviewer.getByRole('button', { name: 'Export listening labels', exact: true }).click());
  const labels = JSON.parse(labelsBytes.toString()); assert.equal(labels.packet_sha256, packet.sha256); assert.equal(labels.independent_ground_truth, false); assert.equal(labels.labels.length, 1);
  await reviewer.getByRole('button', { name: 'Remove observation 1' }).click();
  await reviewer.getByLabel('Restore exported labels').setInputFiles({ name: 'labels.json', mimeType: 'application/json', buffer: labelsBytes });
  await reviewer.getByText('Saved review labels restored.').waitFor();
  const bad = { ...packet, reference: { ...packet.reference, tuning: 'tampered' } };
  reviewer.once('dialog', d => d.accept());
  await reviewer.getByLabel('Open listening packet').setInputFiles({ name: 'tampered.json', mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(bad)) });
  await reviewer.getByText('Packet checksum mismatch.', { exact: false }).waitFor();
  assert.deepEqual(errors, []);
  console.log('PASS: silent input makes zero comparison calls; usable synthetic input comparison; local three-second input check; prediction-free packet export; isolated reviewer makes zero API calls; checksum validation; annotation/export/restore; tampering rejection. No browser exceptions. Synthetic/mocked only.');
} finally { await browser.close(); }
