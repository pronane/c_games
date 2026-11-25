// API-readable results: notices are retrievable via check-run annotations even
// when the video artifact host cannot be reached by the reviewing agent.
import fs from 'node:fs';
import path from 'node:path';
const dir = process.argv[2];
// Publish startup evidence for every leg even when no frame/state was produced.
const parent = dir ? path.dirname(dir) : '';
for (const leg of ['original', 'lod', 'match']) {
  const log = path.join(parent, leg, 'console.log');
  if (!fs.existsSync(log)) continue;
  const lines = fs.readFileSync(log, 'utf8').split(/\r?\n/)
    .filter(line => /AB_BOOT|CAPTURE_READY|CAPTURE_NOT_READY|CAPTURE_TIMEOUT|LOAD_FAILED|SERVER_FAILED|Error|error|failed|RENDER PROCESS GONE/.test(line)).slice(-8);
  if (lines.length) {
    const message = lines.map(s => s.slice(0, 350)).join(' | ').replace(/%/g, '%25');
    console.log(`::notice title=Capture startup ${leg}::${message}`);
  }
}
const files = dir && fs.existsSync(dir) ? fs.readdirSync(dir).filter(f => /^state-\d+\.json$/.test(f)).sort() : [];
const samples = files.map(f => JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8')));
if (samples.length < 12) {
  console.error(`::error::Scripted gameplay capture missing/too short: ${samples.length} states`);
  process.exitCode = 1;
} else {
  const gameplay = samples.filter(s => s.mode !== 'celebration');
  const badBall = gameplay.filter(s => !s.ballNdc || s.ballNdc.some(n => !Number.isFinite(n)) || Math.abs(s.ballNdc[0]) > 0.78 || Math.abs(s.ballNdc[1]) > 0.78 || Math.abs(s.ballNdc[2]) > 1);
  const tickErrors = samples.filter((s, i) => i > 0 && s.tick - samples[i - 1].tick !== 30).length;
  const last = samples.at(-1);
  const report = {
    samples: samples.length, firstTick: samples[0].tick, lastTick: last.tick,
    tickErrors, ballOutOfFrameSamples: badBall.length,
    minBallMinorPixels: Math.min(...samples.map(s => s.ballMinorPixels)),
    locator: 'always-on 14px canvas (~9.6px ring); physics size unchanged',
    meanPlayersWithin5m: +(samples.reduce((n, s) => n + s.crowd5, 0) / samples.length).toFixed(2),
    camera: last.camera, sim: last.sim, motion: last.motion ?? null, team: last.team ?? null,
    motionFallbackSamples: samples.filter(s => s.motionLoaded === false).length,
  };
  if (report.motionFallbackSamples) console.warn(`::warning::AME unavailable in ${report.motionFallbackSamples} captured samples; legacy animation fallback is not AME validation`);
  const motion = report.motion;
  if (!(motion?.contactFootSamples > 0)) console.warn('::warning::No contact-foot observations: foot sliding remains unverified (the shipped manifest has no authored plant frames)');
  const motionFailure = !motion || !(motion.samples > 0) || !Number.isFinite(motion.maxBackwardsSeconds) || motion.maxBackwardsSeconds > 0.5 || report.motionFallbackSamples > 0;
  if (motionFailure) console.error(`::error::Runtime motion evidence missing, AME fallback, or sustained backwards travel above 0.5s: ${JSON.stringify(motion)}`);
  const text = JSON.stringify(report);
  console.log(`::notice title=Scripted gameplay measurements::${text}`);
  fs.writeFileSync(path.join(dir, 'gameplay-review.json'), JSON.stringify(report, null, 2));
  if (process.env.GITHUB_STEP_SUMMARY) fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, `\n## Scripted gameplay measurements\n\n\`\`\`json\n${JSON.stringify(report, null, 2)}\n\`\`\`\n\nMeasurements are not visual sign-off. Celebration framing excluded.\n`);
  if (!gameplay.length || badBall.length || tickErrors || motionFailure) {
    console.error(`::error::Gameplay capture failed: normal-play samples=${gameplay.length}, ball failures=${badBall.length}, tick errors=${tickErrors}`);
    process.exitCode = 1;
  }
}
