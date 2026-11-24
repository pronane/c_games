// Experimental SwiftShader capture tripwire; not a GPU or occlusion test.
import fs from 'node:fs';
import { parseAbCamStats } from './ab_stats.mjs';
let failed = process.argv.length < 3;
for (const file of process.argv.slice(2)) {
  const samples = fs.existsSync(file) ? parseAbCamStats(fs.readFileSync(file, 'utf8')) : [];
  const ok = samples.length > 0 && samples.every(s => s.ball_in === 100 && s.ball_max_ndc <= 0.78 && (s.player_in === null || (s.player_in === 100 && s.player_max_ndc <= 0.78)));
  console.log(`${ok ? 'PASS' : 'FAIL'} ${file}: ${samples.length} visibility samples (player n/a is not player coverage)`);
  if (!ok) failed = true;
}
process.exitCode = failed ? 1 : 0;
