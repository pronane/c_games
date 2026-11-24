#!/usr/bin/env node
/**
 * Aggregate the `AB_STATS ...` lines that the app logs every ~2 s in ?ab=1
 * mode (rAF frame-time percentiles over a sliding 240-frame window + three.js
 * renderer.info counters) into a markdown percentile table.
 *
 * Honesty contract: these numbers come from SwiftShader software WebGL on a
 * GPU-less CI runner. They are a REGRESSION TRIPWIRE for the capture legs,
 * not a GPU performance claim — real GPU/browser verification is a separate
 * human step (see docs/GAP_ANALYSIS_PS5.md, P0 "verify gap").
 *
 * Usage: node tools/ab_stats.mjs <logOrDir> [<logOrDir> ...]
 *   Each argument is a leg: a directory containing electron.log, or a log file
 *   directly. Leg label = directory name, or the file basename minus .log.
 * Always exits 0 (diagnostics only) — prints the table to stdout.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const LINE = /AB_STATS fps=([\d.]+) p50_ms=([\d.]+) p95_ms=([\d.]+) tris=(\d+) calls=(\d+) textures=(\d+) geometries=(\d+) lod=([a-z]+)/g;

/** Pure: extract every AB_STATS sample from an electron console log. */
export function parseAbStats(text) {
  const out = [];
  for (const m of text.matchAll(LINE)) {
    out.push({
      fps: Number(m[1]),
      p50_ms: Number(m[2]),
      p95_ms: Number(m[3]),
      tris: Number(m[4]),
      calls: Number(m[5]),
      textures: Number(m[6]),
      geometries: Number(m[7]),
      lod: m[8],
    });
  }
  return out;
}

const mean = (xs) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : NaN);
const max = (xs) => (xs.length ? Math.max(...xs) : NaN);
const min = (xs) => (xs.length ? Math.min(...xs) : NaN);
const f = (n, d = 1) => (Number.isFinite(n) ? n.toFixed(d) : '—');

/** Pure: one markdown table row for a leg's samples (null when empty). */
export function summariseLeg(label, samples) {
  if (!samples || samples.length === 0) return `| \`${label}\` | 0 | no samples captured | — | — | — | — | — | — | — |`;
  const fps = samples.map((s) => s.fps);
  const p50 = samples.map((s) => s.p50_ms);
  const p95 = samples.map((s) => s.p95_ms);
  const tris = samples.map((s) => s.tris);
  const calls = samples.map((s) => s.calls);
  const last = samples[samples.length - 1];
  return `| \`${label}\` | ${samples.length} | ${f(mean(fps))} / ${f(min(fps))} | ${f(mean(p50))} / ${f(max(p50))} | ${f(mean(p95))} / ${f(max(p95))} | ${last.tris} | ${f(mean(calls))} / ${max(calls)} | ${last.textures} | ${last.geometries} | ${last.lod} |`;
}

function loadLog(arg) {
  const stat = fs.existsSync(arg) ? fs.statSync(arg) : null;
  if (stat?.isDirectory()) {
    return { label: path.basename(path.resolve(arg)), file: path.join(arg, 'electron.log') };
  }
  const label = path.basename(arg).replace(/\.(log|txt)$/i, '') || arg;
  return { label, file: arg };
}

export function main(argv) {
  const legs = argv.map(loadLog);
  const lines = [
    '## Renderer perf (software WebGL — CI tripwire, not a GPU claim)',
    '',
    '| leg | samples | fps avg / min | p50 ms avg / max | p95 ms avg / max | tris (last) | calls avg / max | textures (last) | geometries (last) | lod |',
    '|---|---|---|---|---|---|---|---|---|---|',
  ];
  for (const { label, file } of legs) {
    let samples = [];
    try {
      samples = parseAbStats(fs.readFileSync(file, 'utf8'));
    } catch {
      samples = [];
    }
    lines.push(summariseLeg(label, samples));
  }
  lines.push('');
  lines.push('_SwiftShader software rendering on a GPU-less runner: relative frame-time trend between legs, never an absolute FPS claim. GPU verification is a human step (GAP_ANALYSIS_PS5.md, P0)._');
  console.log(lines.join('\n'));
}

const invokedAsScript =
  typeof process !== 'undefined' &&
  process.argv[1] &&
  fileURLToPath(import.meta.url) === path.resolve(process.argv[1]);

if (invokedAsScript) {
  main(process.argv.slice(2));
}
