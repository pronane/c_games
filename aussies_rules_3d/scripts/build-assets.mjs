/**
 * Build the game's 3D assets with Blender (bpy as a Python module):
 * rigged+animated players, the Sherrin ball and the Melbourne arena.
 *
 *   node scripts/build-assets.mjs              all assets
 *   node scripts/build-assets.mjs player ball  only some
 *
 * Handles headless servers without an X11/Mesa stack by building small stub
 * libraries (see tools/blender/headless_stubs.sh).
 */
import { spawnSync } from 'node:child_process';
import { existsSync, readdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const BLENDER_DIR = path.join(ROOT, 'tools', 'blender');
const VENV = path.join(BLENDER_DIR, '.venv');
const VENV_PY = process.platform === 'win32'
  ? path.join(VENV, 'Scripts', 'python.exe')
  : path.join(VENV, 'bin', 'python');
const ONLY = process.argv.slice(2);

function say(msg) {
  process.stdout.write(`${msg}\n`);
}

const BASE_PYTHON = process.platform === 'win32' ? 'python' : 'python3';

function run(cmd, args, opts = {}) {
  // shell:true lets Windows resolve .cmd/.exe shims (e.g. python from the Store).
  const res = spawnSync(cmd, args, {
    stdio: 'inherit',
    shell: process.platform === 'win32',
    ...opts,
  });
  if (res.error) {
    say(`Could not launch \`${cmd}\`: ${res.error.message}`);
    return false;
  }
  return res.status === 0;
}

say('Aussie Rules 3D — 3D asset pipeline (Blender / bpy)');
say('===================================================');

// 1. python
const python = existsSync(VENV_PY) ? VENV_PY : BASE_PYTHON;
if (!existsSync(VENV_PY)) {
  say('→ creating a private Python environment in tools/blender/.venv');
  if (!run(BASE_PYTHON, ['-m', 'venv', VENV], { cwd: BLENDER_DIR })) {
    say('Could not create the Python venv — install Python 3.10+ and re-run.');
    process.exit(1);
  }
}

// 2. bpy (Blender as a module)
const probe = spawnSync(python, ['-c', 'import bpy; print(bpy.app.version_string)'], {
  cwd: BLENDER_DIR,
  encoding: 'utf8',
});
if (probe.status !== 0) {
  say('→ installing Blender (the bpy module, ~300 MB — one-time)…');
  if (!run(python, ['-m', 'pip', 'install', '--upgrade', 'pip'], { cwd: BLENDER_DIR })) {
    process.exit(1);
  }
  if (
    !run(python, ['-m', 'pip', 'install', '-r', path.join(BLENDER_DIR, 'requirements.txt')], {
      cwd: BLENDER_DIR,
    })
  ) {
    say('Failed to install bpy — check your network (pypi.org) and re-run.');
    process.exit(1);
  }
} else {
  say(`✓ Blender ${probe.stdout.trim()} (bpy)`);
}

// 3. headless stubs when the X/GL stack is missing (Linux servers only)
let env = process.env;
if (process.platform === 'linux') {
  const soPath = existsSync(path.join(BLENDER_DIR, '.venv', 'lib'))
    ? readdirSync(path.join(BLENDER_DIR, '.venv', 'lib'))[0]
    : null;
  const probe2 = spawnSync(python, ['-c', 'import bpy'], { cwd: BLENDER_DIR, encoding: 'utf8' });
  if (probe2.status !== 0 && /libX|libGL|libxkb|libICE|libSM/.test(probe2.stderr ?? '')) {
    say('→ building headless stub libraries for the missing X/GL stack…');
    run('bash', [path.join(BLENDER_DIR, 'headless_stubs.sh')], { cwd: BLENDER_DIR });
    env = { ...process.env, LD_LIBRARY_PATH: [path.join(BLENDER_DIR, 'stubs'), process.env.LD_LIBRARY_PATH ?? ''].join(':') };
  }
  void soPath;
}

// 4. generate
const args = ['build_assets.py', ...ONLY];
say('→ generating assets (players rigged & animated, ball, stadium)…');
if (!run(python, args, { cwd: BLENDER_DIR, env })) {
  say('Asset generation failed.');
  process.exit(1);
}

// 5. verify
const outDir = path.join(ROOT, 'public', 'assets');
for (const f of ['player.glb', 'ball.glb', 'stadium.glb']) {
  const p = path.join(outDir, f);
  if (!existsSync(p)) {
    say(`✗ missing ${p}`);
    process.exit(1);
  }
  say(`✓ ${path.relative(ROOT, p)}`);
}
say('Done.');
