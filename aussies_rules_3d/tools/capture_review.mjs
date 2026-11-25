// API-readable results: notices are retrievable via check-run annotations even
// when the video artifact host cannot be reached by the reviewing agent.
import fs from 'node:fs';
import path from 'node:path';
const dir = process.argv[2];
const files = dir && fs.existsSync(dir) ? fs.readdirSync(dir).filter(f => /^state-\d+\.json$/.test(f)).sort() : [];
// Six low-resolution game frames, bounded well below annotation message limits.
// This is a fallback for artifact-host restrictions, not a replacement for MP4s.
if (dir && fs.existsSync(dir)) for (const file of fs.readdirSync(dir).filter(f => /^preview-\d+\.jpg$/.test(f)).sort().slice(0, 6)) {
  const bytes = fs.readFileSync(path.join(dir, file));
  if (bytes.length <= 40000) console.log(`::notice title=GAMEPLAY_PREVIEW_${file.match(/\d+/)[0]}::${bytes.toString('base64')}`);
  else console.warn(`::warning::Preview too large for annotation: ${file}`);
}
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
    camera: last.camera, sim: last.sim,
  };
  const text = JSON.stringify(report);
  console.log(`::notice title=Scripted gameplay measurements::${text}`);
  fs.writeFileSync(path.join(dir, 'gameplay-review.json'), JSON.stringify(report, null, 2));
  if (process.env.GITHUB_STEP_SUMMARY) fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY, `\n## Scripted gameplay measurements\n\n\`\`\`json\n${JSON.stringify(report, null, 2)}\n\`\`\`\n\nMeasurements are not visual sign-off. Celebration framing excluded.\n`);
  if (!gameplay.length || badBall.length || tickErrors) {
    console.error(`::error::Gameplay capture failed: normal-play samples=${gameplay.length}, ball failures=${badBall.length}, tick errors=${tickErrors}`);
    process.exitCode = 1;
  }
}
