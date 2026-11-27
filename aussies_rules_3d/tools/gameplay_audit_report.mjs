import fs from 'node:fs';
const file = process.argv[2] ?? 'build/gameplay-audit/simulation.json';
const rows = JSON.parse(fs.readFileSync(file, 'utf8'));
const summary = rows.map(r => ({ seed: r.seed, seconds: r.simulatedSeconds,
  liveSeconds: +r.diagnostics.liveSeconds.toFixed(2), freeEvents: r.diagnostics.frees,
  freesByReason: r.diagnostics.freesByReason, restartEvents: r.diagnostics.ballUps,
  tackles: r.diagnostics.tackles, backwardsSamples: r.backwards,
  runningSamples: r.runningSamples, meanLiveCrowd5: +r.meanLiveCrowd5.toFixed(2) }));
for (const row of summary) console.log(`::notice title=Seeded gameplay audit::${JSON.stringify(row)}`);
if (process.env.GITHUB_STEP_SUMMARY) fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY,
  `\n## Seeded simulation audit (not visual sign-off)\n\nFree events include marks/boundary awards; they are not all tackle infringements. Whistle counts require the browser capture.\n\n\`\`\`json\n${JSON.stringify(summary, null, 2)}\n\`\`\`\n`);
