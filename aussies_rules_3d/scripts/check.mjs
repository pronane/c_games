/**
 * Verification harness — proves the build is healthy end-to-end:
 *   1. TypeScript compiles cleanly
 *   2. The full test suite passes (laws, engine, input, sim)
 *   3. The production build succeeds
 *   4. The 3D assets are valid glTF binaries
 *
 *   node scripts/check.mjs
 */
import { spawnSync } from 'node:child_process';
import { existsSync, openSync, readSync, closeSync, statSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const results = [];

function check(name, fn) {
  try {
    const detail = fn();
    results.push({ name, ok: true, detail: detail ?? '' });
    process.stdout.write(`  ✓ ${name}${detail ? ` — ${detail}` : ''}\n`);
  } catch (err) {
    results.push({ name, ok: false, detail: String(err) });
    process.stdout.write(`  ✗ ${name} — ${err}\n`);
  }
}

function run(cmd, args) {
  return spawnSync(cmd, args, { cwd: ROOT, encoding: 'utf8' });
}

console.log('Aussie Rules 3D — verification');
console.log('==============================');

check('TypeScript compiles', () => {
  const res = run('npx', ['tsc', '--noEmit']);
  if (res.status !== 0) throw new Error(`tsc failed:\n${res.stdout}\n${res.stderr}`);
  return 'no errors';
});

check('test suite', () => {
  const res = run('npx', ['vitest', 'run']);
  const m = (res.stdout ?? '').match(/Tests\s+(.+)\n/);
  if (res.status !== 0) throw new Error(`vitest failed:\n${res.stdout}\n${res.stderr}`);
  return m ? m[1].trim() : 'all passed';
});

check('production build', () => {
  const res = run('npx', ['vite', 'build']);
  if (res.status !== 0) throw new Error(`build failed:\n${res.stdout}\n${res.stderr}`);
  return 'dist/ written';
});

check('3D assets are valid glTF binaries', () => {
  const details = [];
  for (const f of ['player.glb', 'ball.glb', 'stadium.glb']) {
    const p = path.join(ROOT, 'public', 'assets', f);
    if (!existsSync(p)) throw new Error(`${f} missing`);
    const fd = openSync(p, 'r');
    const buf = Buffer.alloc(12);
    readSync(fd, buf, 0, 12, 0);
    closeSync(fd);
    if (buf.toString('latin1', 0, 4) !== 'glTF') throw new Error(`${f} is not a glTF binary`);
    details.push(`${f} ${(statSync(p).size / 1024).toFixed(0)}KB`);
  }
  return details.join(', ');
});

const failed = results.filter((r) => !r.ok);
console.log('==============================');
console.log(
  failed.length === 0
    ? `All ${results.length} checks passed.`
    : `${failed.length}/${results.length} checks FAILED.`
);
process.exit(failed.length === 0 ? 0 : 1);
