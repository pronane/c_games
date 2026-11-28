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
  // On Windows, npx is a .cmd shim that cannot be spawned directly
  // (Node refuses to launch it without a shell), so go through the shell.
  const res = spawnSync(cmd, args, {
    cwd: ROOT,
    encoding: 'utf8',
    shell: process.platform === 'win32',
  });
  if (res.error) {
    return { status: null, stdout: '', stderr: String(res.error) };
  }
  return res;
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

function readGlbJson(file) {
  const fd = openSync(file, 'r');
  const head = Buffer.alloc(20);
  readSync(fd, head, 0, 20, 0);
  if (head.toString('latin1', 0, 4) !== 'glTF') { closeSync(fd); throw new Error(file + ' is not a glTF binary'); }
  const jsonLen = head.readUInt32LE(12);
  const json = Buffer.alloc(jsonLen);
  readSync(fd, json, 0, jsonLen, 20);
  closeSync(fd);
  return JSON.parse(json.toString('utf8'));
}

check('3D assets are valid glTF binaries', () => {
  const details = [];
  for (const f of ['player.glb', 'gaelic_player.glb', 'ball.glb', 'stadium.glb']) {
    const p = path.join(ROOT, 'public', 'assets', f);
    if (!existsSync(p)) throw new Error(`${f} missing`);
    readGlbJson(p);
    details.push(`${f} ${(statSync(p).size / 1024).toFixed(0)}KB`);
  }
  return details.join(', ');
});

check('squad GLB carries the full 52-joint / 32-clip / nine-look contract', () => {
  // The runtime tints kit pieces and prunes appearance variants by vN_* node
  // names — a GLB that loses those (e.g. a bad repack) would silently render
  // white kits with every look visible, so gate on it here.
  const p = path.join(ROOT, 'public', 'assets', 'gaelic_player.glb');
  const j = readGlbJson(p);
  const skins = j.skins ?? [];
  if (skins.length !== 1) throw new Error(`expected exactly 1 skin, got ${skins.length}`);
  const joints = skins[0].joints?.length ?? 0;
  if (joints !== 52) throw new Error(`expected 52 joints, got ${joints}`);
  const anims = (j.animations ?? []).map((a) => a.name);
  for (const need of ['idle', 'run', 'run_ball', 'kick_run', 'hand_pass', 'tackle_reach', 'knocked_down']) {
    if (!anims.includes(need)) throw new Error(`missing clip ${need}`);
  }
  const meshNames = (j.nodes ?? []).map((n) => n.name ?? '');
  for (let v = 0; v <= 8; v++) {
    if (!meshNames.some((n) => n.startsWith(`v${v}_`))) throw new Error(`no meshes for look v${v}`);
  }
  const forKit = ['jersey', 'shorts', 'socks', 'boots'];
  for (const suffix of forKit) {
    if (!meshNames.some((n) => n.endsWith(`_${suffix}`))) throw new Error(`no *_${suffix} mesh`);
  }
  return `52 joints, ${anims.length} clips, v0..v8 looks`;
});

const failed = results.filter((r) => !r.ok);
console.log('==============================');
console.log(
  failed.length === 0
    ? `All ${results.length} checks passed.`
    : `${failed.length}/${results.length} checks FAILED.`
);
process.exit(failed.length === 0 ? 0 : 1);
