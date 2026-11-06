/**
 * Aussie Rules 3D — one-click installer (orchestrated from install.sh /
 * install.ps1). Installs dependencies, verifies the 3D assets and, when the
 * Blender pipeline is available, can regenerate them from source.
 *
 *   node scripts/install.mjs           full setup
 *   node scripts/install.mjs --check   report what is present, change nothing
 *   node scripts/install.mjs --assets  also (re)generate the 3D assets with Blender
 */
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync } from 'node:fs';
import { homedir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const args = new Set(process.argv.slice(2));
const CHECK_ONLY = args.has('--check');
const WANT_ASSETS = args.has('--assets');

function say(msg) {
  process.stdout.write(`${msg}\n`);
}

function run(cmd, cmdArgs, opts = {}) {
  const res = spawnSync(cmd, cmdArgs, { stdio: 'inherit', cwd: ROOT, ...opts });
  return res.status === 0;
}

say('Aussie Rules 3D — installer');
say('============================');

// 1. Node version
const major = Number(process.versions.node.split('.')[0]);
if (major < 20) {
  say(`Node ${process.versions.node} is too old — Node 20+ is required.`);
  say('Install it from https://nodejs.org (or via nvm/fnm) and run this again.');
  process.exit(1);
}
say(`✓ Node ${process.versions.node}`);

// 2. Dependencies
const haveModules = existsSync(path.join(ROOT, 'node_modules', 'three'));
if (CHECK_ONLY) {
  say(haveModules ? '✓ dependencies installed' : '✗ dependencies missing (run ./install.sh)');
} else if (haveModules) {
  say('✓ dependencies already installed');
} else {
  say('→ installing npm dependencies (three, vite, vitest, typescript)…');
  if (!run('npm', ['install', '--no-audit', '--no-fund'])) {
    say('npm install failed — check your network connection and try again.');
    process.exit(1);
  }
  say('✓ dependencies installed');
}

// 3. 3D assets (rigged player, ball, Melbourne arena)
const assets = ['player.glb', 'ball.glb', 'stadium.glb'].map((f) =>
  path.join(ROOT, 'public', 'assets', f)
);
const assetsPresent = assets.every((a) => existsSync(a));
if (assetsPresent && !WANT_ASSETS) {
  say('✓ 3D assets present (rigged players, ball, arena)');
} else if (CHECK_ONLY) {
  say(assetsPresent ? '✓ 3D assets present' : '✗ 3D assets missing (run ./install.sh --assets)');
} else {
  say('→ generating 3D assets with Blender (this can take a minute)…');
  const ok = run(process.execPath, [path.join(ROOT, 'scripts', 'build-assets.mjs')]);
  if (!ok) {
    if (assetsPresent) {
      say('⚠ asset regeneration failed — continuing with the committed assets.');
    } else {
      say('Asset generation failed and no committed assets were found.');
      say('Install Python 3.10+ and re-run, or restore public/assets/*.glb from git.');
      process.exit(1);
    }
  }
}

// 4. Cache dir for the PWA
mkdirSync(path.join(ROOT, 'dist'), { recursive: true });
try {
  mkdirSync(path.join(homedir(), '.aussie-rules-3d'), { recursive: true });
} catch {
  /* not fatal */
}

say('');
say('All set! Start the game with:  ./start.sh   (Windows: start.cmd)');
say('Or for development with hot reload:  npm run dev');
