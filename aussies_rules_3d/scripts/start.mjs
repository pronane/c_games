/**
 * Aussie Rules 3D — one-click runner (orchestrated from start.sh / start.cmd).
 *
 *   node scripts/start.mjs            build once, serve at http://localhost:8080
 *   node scripts/start.mjs --dev      development server with hot reload
 *   node scripts/start.mjs --port N   use port N
 *   node scripts/start.mjs --no-open  don't try to open a browser
 */
import { spawn, spawnSync } from 'node:child_process';
import { existsSync, createReadStream, statSync } from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const args = process.argv.slice(2);
const DEV = args.includes('--dev');
const NO_OPEN = args.includes('--no-open') || !!process.env.CI;
const portArg = args.indexOf('--port');
const PORT = Number(
  portArg >= 0 ? args[portArg + 1] : process.env.PORT || 8080
);

const IS_WIN = process.platform === 'win32';
// On Windows, npm/npx are .cmd shims that cannot be spawned directly
// (Node refuses to launch them without a shell), so go through the shell.
function run(cmd, cmdArgs) {
  const res = spawnSync(cmd, cmdArgs, { stdio: 'inherit', cwd: ROOT, shell: IS_WIN });
  if (res.error) {
    console.error(`Could not launch \`${cmd}\`: ${res.error.message}`);
    process.exit(1);
  }
  if (res.status !== 0) process.exit(res.status ?? 1);
}

if (DEV) {
  const child = spawn('npx', ['vite', '--host', '0.0.0.0', '--port', String(PORT)], {
    stdio: 'inherit',
    cwd: ROOT,
    shell: IS_WIN,
  });
  child.on('error', (err) => {
    console.error(`Could not launch vite: ${err.message}`);
    process.exit(1);
  });
  child.on('exit', (code) => process.exit(code ?? 0));
} else {
  if (!existsSync(path.join(ROOT, 'node_modules', 'three'))) {
    console.log('Dependencies are missing — running the installer first…');
    run(process.execPath, [path.join(ROOT, 'scripts', 'install.mjs')]);
  }
  console.log('Building Aussie Rules 3D…');
  run('npx', ['vite', 'build']);

  const DIST = path.join(ROOT, 'dist');
  const MIME = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.json': 'application/json',
    '.webmanifest': 'application/manifest+json',
    '.glb': 'model/gltf-binary',
    '.svg': 'image/svg+xml',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.wav': 'audio/wav',
    '.mp3': 'audio/mpeg',
  };

  const server = http.createServer((req, res) => {
    try {
      const url = new URL(req.url ?? '/', 'http://localhost');
      let rel = decodeURIComponent(url.pathname);
      if (rel.endsWith('/')) rel += 'index.html';
      const file = path.join(DIST, path.normalize(rel).replace(/^([/\\])+/, ''));
      if (!file.startsWith(DIST) || !existsSync(file) || !statSync(file).isFile()) {
        // SPA fallback
        const index = path.join(DIST, 'index.html');
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
        createReadStream(index).pipe(res);
        return;
      }
      const ext = path.extname(file).toLowerCase();
      res.writeHead(200, {
        'Content-Type': MIME[ext] ?? 'application/octet-stream',
        'Cache-Control': ext === '.html' ? 'no-cache' : 'public, max-age=3600',
      });
      createReadStream(file).pipe(res);
    } catch (err) {
      res.writeHead(500);
      res.end(String(err));
    }
  });

  server.listen(PORT, '0.0.0.0', () => {
    const url = `http://localhost:${PORT}/`;
    console.log('');
    console.log(`  🏉 Aussie Rules 3D is running at ${url}`);
    console.log('     (open it in any browser — desktop, phone, tablet, TV)');
    console.log('');
    if (!NO_OPEN) {
      // 'start' is a cmd.exe builtin, not an executable — it must go through the shell.
      const [opener, openerArgs] =
        process.platform === 'darwin'
          ? ['open', [url]]
          : process.platform === 'win32'
            ? ['cmd.exe', ['/c', 'start', '', url]]
            : ['xdg-open', [url]];
      try {
        spawn(opener, openerArgs, { stdio: 'ignore', detached: true, shell: false }).on('error', () => {});
      } catch {
        /* ignore */
      }
    }
  });
}
