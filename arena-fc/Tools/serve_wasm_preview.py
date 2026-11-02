#!/usr/bin/env python3
"""Serve the Arena FC browser edition using the Godot 4.7.2 WebAssembly runtime.

    python3 Tools/serve_wasm_preview.py [--port 8080] [--no-serve]

Why this exists: Godot 4 cannot export C# projects to the Web, so the `web`
target of build.py is a GDScript-only copy.  When no Godot editor / export
templates are available this tool runs that same project directly in the
browser using the WASM engine from npm, staging the loose files into the
engine's MEMFS.  It needs Node/npm on PATH the first time (to fetch the engine).

IMPORTANT: Godot's Web input callbacks are attached to the CANVAS element, so
the canvas must be focusable (tabindex) and focused - otherwise keyboard and
camera controls silently do nothing.  The generated page handles that.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(os.environ.get('ARENA_FC_CACHE', Path.home() / '.cache' / 'arena-fc')) / 'wasm'
PKG = '@ringozz/godot-web-wasm32@4.7.2-685'
WASM_JS = 'godot.web.template_release.wasm32.nothreads.js'
WASM_BIN = 'godot.web.template_release.wasm32.nothreads.wasm'
WORKLETS = ('audio.worklet.js', 'audio.position.worklet.js')
ALLOW = {'.gd', '.tscn', '.tres', '.txt', '.json', '.svg', '.gdshader', '.cfg'}
SKIP = {'.git', '.godot', 'out', 'obj', 'bin', 'media', 'screenshots', 'node_modules', 'build'}


def runtime_files() -> Path:
    gen = CACHE / 'webpkg' / 'package' / 'gen'
    if (gen / WASM_BIN).exists():
        return gen
    CACHE.mkdir(parents=True, exist_ok=True)
    print(f'fetching {PKG} …', flush=True)
    subprocess.run(['npm', 'pack', PKG], cwd=CACHE, check=True, capture_output=True, text=True)
    tgz = next(CACHE.glob('*.tgz'))
    with tarfile.open(tgz) as t:
        t.extractall(CACHE / 'webpkg')
    return gen


def build_site(out: Path) -> None:
    gen = runtime_files()
    if out.exists():
        shutil.rmtree(out)
    (out / 'files').mkdir(parents=True)
    shutil.copy2(gen / WASM_JS, out / 'godot.mjs')
    shutil.copy2(gen / WASM_BIN, out / 'godot.wasm')
    for name in WORKLETS:
        shutil.copy2(gen / name, out / name)

    manifest = []
    for src in sorted(ROOT.rglob('*')):
        if not src.is_file():
            continue
        rel = src.relative_to(ROOT)
        if any(p in SKIP for p in rel.parts) or src.suffix.lower() not in ALLOW:
            continue
        if rel.as_posix() == 'project.godot':
            continue
        dest = out / 'files' / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        manifest.append(rel.as_posix())

    cfg = (ROOT / 'project.godot').read_text()
    cfg = cfg.replace('run/main_scene="res://Scenes/Main.tscn"',
                      'run/main_scene="res://Web/BrowserMain.tscn"')
    cfg = re.sub(r'\n\[dotnet\]\n(?:.*\n)*?(?=\n\[|\Z)', '\n', cfg)
    cfg = cfg.replace(', "C#"', '').replace('config/name="Arena FC"',
                                            'config/name="Arena FC Browser Edition"')
    (out / 'files' / 'project.godot').write_text(cfg)
    manifest.append('project.godot')
    (out / 'manifest.json').write_text(json.dumps(sorted(manifest), indent=1))

    (out / 'boot.mjs').write_text(BOOT_JS)
    (out / 'index.html').write_text(INDEX_HTML)
    (out / 'serve.py').write_text(SERVE_PY)
    print(f'built {len(manifest)} project files into {out}', flush=True)


BOOT_JS = '''import Godot from './godot.mjs';

const canvas = document.getElementById('canvas');
const status = document.getElementById('status');
const hint = document.getElementById('focus-hint');
const say = (s) => { status.textContent = s; console.log('[preview]', s); };

// Godot Web attaches keydown/keyup to the canvas.  It MUST be focusable and
// focused or no keyboard / camera key ever reaches the game.
const focus = () => { if (document.activeElement !== canvas) canvas.focus(); };
canvas.addEventListener('pointerdown', focus);
window.addEventListener('keydown', (e) => {
  if (document.activeElement !== canvas && !e.metaKey && !e.ctrlKey) focus();
}, { passive: true });

const Module = await Godot({
  canvas,
  noExitRuntime: true,
  locateFile: (p) => {
    if (p.endsWith('.wasm')) return './godot.wasm';
    if (p.endsWith('audio.position.worklet.js')) return './audio.position.worklet.js';
    if (p.endsWith('audio.worklet.js')) return './audio.worklet.js';
    return './' + p;
  },
  print: (...a) => console.log(...a),
  printErr: (...a) => console.error(...a),
});
Module.initConfig({ canvas, canvasResizePolicy: 2, focusCanvas: true });

say('staging Arena FC project …');
const manifest = await (await fetch('./manifest.json')).json();
for (const f of manifest) {
  const r = await fetch('./files/' + f);
  if (!r.ok) throw new Error('missing ' + f);
  Module.copyToFS('/' + f, new Uint8Array(await r.arrayBuffer()));
}
say('starting Arena FC …');
status.classList.add('hidden');
focus();
Module.callMain(['--path', '/']);
canvas.addEventListener('pointerdown', () => { if (hint) hint.classList.add('hidden'); });
'''

INDEX_HTML = '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Arena FC — live preview</title>
<style>
  html, body { margin:0; height:100%; background:#0b1220; color:#e6edf3;
               font:14px/1.5 system-ui, sans-serif; overflow:hidden; }
  #wrap { position:relative; width:100vw; height:100vh; }
  /* tabindex + outline:none: Godot binds keyboard events to the canvas itself. */
  #canvas { width:100%; height:100%; display:block; background:#0b1220;
            outline:none; touch-action:none; }
  #status { position:absolute; inset:0; display:grid; place-items:center;
            font-size:18px; background:#0b1220; z-index:2; }
  #status.hidden { display:none; }
  #focus-hint { position:absolute; top:10px; left:50%; transform:translateX(-50%);
                z-index:3; background:#10243a; border:1px solid #2bdb85; color:#d8ffe9;
                padding:6px 14px; border-radius:18px; font-size:12px;
                pointer-events:none; }
  #focus-hint.hidden { display:none; }
  #keys { position:absolute; left:12px; bottom:10px; z-index:3; opacity:.7;
          pointer-events:none; font-size:12px; }
</style>
</head>
<body>
<div id="wrap">
  <div id="status">Loading Godot 4.7.2 …</div>
  <div id="focus-hint">Click the game once to focus it, then use the keyboard / pad</div>
  <canvas id="canvas" tabindex="0" width="1280" height="720"></canvas>
  <div id="keys">Menu: mouse, arrows + Enter, or pad d-pad + A/Start · WASD / stick move · E pass · Q through · F tackle · SPACE shoot · TAB switch · C / 1-4 / pad R3 camera · wheel or +/- zoom · ESC menu</div>
</div>
<script type="module" src="./boot.mjs"></script>
</body>
</html>
'''

SERVE_PY = '''#!/usr/bin/env python3
import http.server, socketserver, os, sys
class H(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        super().end_headers()
    def guess_type(self, path):
        if path.endswith('.wasm'): return 'application/wasm'
        if path.endswith('.pck'): return 'application/octet-stream'
        return super().guess_type(path)
os.chdir(os.path.dirname(os.path.abspath(__file__)))
socketserver.TCPServer.allow_reuse_address = True
port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
with socketserver.TCPServer(('0.0.0.0', port), H) as s:
    print(f'Arena FC preview on http://0.0.0.0:{port}/', flush=True)
    s.serve_forever()
'''


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', type=int, default=8080)
    ap.add_argument('--out', default=str(ROOT / 'build' / 'wasm_preview'))
    ap.add_argument('--no-serve', action='store_true', help='build the site only')
    a = ap.parse_args()
    out = Path(a.out).resolve()
    build_site(out)
    if a.no_serve:
        return
    os.chdir(out)
    subprocess.run([sys.executable, str(out / 'serve.py'), str(a.port)], check=True)


if __name__ == '__main__':
    main()
