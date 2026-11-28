// Experimental SwiftShader capture tripwire; not a GPU or occlusion test.
import fs from 'node:fs';
import { parseAbCamStats } from './ab_stats.mjs';
const args = process.argv.slice(2);
const requirePlayer = args.includes('--require-player');
const allowDistant = args.includes('--allow-distant-player');
const files = args.filter(a => !['--require-player', '--allow-distant-player'].includes(a));
let failed = files.length === 0;
if (failed) console.error('::error::No framing logs supplied');
for (const file of files) {
  const samples = fs.existsSync(file) ? parseAbCamStats(fs.readFileSync(file, 'utf8')) : [];
  const bad = samples.filter(s => s.frames <= 0 || s.ball_in !== 100 || s.ball_max_ndc > 0.78 ||
    (!allowDistant && s.player_in !== null && (s.player_in !== 100 || s.player_max_ndc === null || s.player_max_ndc > 0.78)) ||
    (requirePlayer && s.player_in === null));
  const ok = samples.length >= 2 && bad.length === 0;
  console.log(`${ok ? 'PASS' : 'FAIL'} ${file}: ${samples.length} visibility samples; require-player=${requirePlayer}`);
  if (!ok) {
    console.error(`::error::${file}: ${samples.length < 2 ? 'Missing/insufficient visibility samples' : 'Subject outside safe frame or required player missing'}; failing samples=${JSON.stringify(bad.slice(0, 5))}`);
    failed = true;
  }
}
process.exitCode = failed ? 1 : 0;
