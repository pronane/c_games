#!/usr/bin/env node
/**
 * Bundles tools/video/capture.ts with esbuild and runs it:
 *   node tools/video/export_match.mjs [gameSeconds] [outJson]
 * Picks the most eventful seed of a quick search, then writes per-frame
 * telemetry JSON for the Blender video tool.
 */
import { build } from 'esbuild';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));
const outFile = path.join(here, '.capture.bundle.mjs');

await build({
  entryPoints: [path.join(here, 'capture.ts')],
  bundle: true,
  platform: 'node',
  format: 'esm',
  target: 'node18',
  outfile: outFile,
  logLevel: 'warning',
});

const mod = await import(pathToFileURL(outFile).href);
const gameSeconds = Number(process.argv[2] ?? 260);
const outJson = process.argv[3] ?? path.join(here, 'match_frames.json');

console.log('[video] searching best-of-40 seeds (3 game-min each, ranked by goals)...');
const best = mod.runSearch(40, 180);
console.log('[video] ranked:', best.ranked);
console.log('[video] picked seed', best.seed, 'with', best.goals, 'goals');

console.log(`[video] capturing seed=${best.seed} for ${gameSeconds}s @24fps...`);
const cap = mod.capture(String(best.seed), gameSeconds, 24);
console.log(
  `[video] ${cap.frames.length} frames, goals at ${JSON.stringify(cap.goalFrames)}, ` +
    `${cap.eventFrames.length} event frames`,
);
const fs = await import('node:fs');
fs.writeFileSync(outJson, JSON.stringify(cap));
console.log('[video] wrote', outJson, (fs.statSync(outJson).size / 1e6).toFixed(1) + ' MB');
