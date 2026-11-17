"""Token-protected file drop for a rented machine: a browser upload page (chunked, resumable)
and file downloads, serving /root/xfer on port 8000.

    python training/runpod/filedrop.py <token>

Upload page: https://<pod>-8000.proxy.runpod.net/<token>/upload
Download:    https://<pod>-8000.proxy.runpod.net/<token>/<path under /root/xfer>
Keep the token private: anyone with it can upload to the machine."""
import http.server, os, sys, urllib.parse, json
TOKEN = sys.argv[1]
ROOT = '/root/xfer'
PAGE = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Guitar Lab upload</title><style>
body{font:16px system-ui,sans-serif;max-width:640px;margin:32px auto;padding:0 16px;color:#222;background:#fafafa}
.f{margin:10px 0;padding:10px;border:1px solid #ddd;border-radius:8px;background:#fff}
progress{width:100%;height:14px}button{font-size:16px;padding:8px 14px}</style></head><body>
<h2>Send multitrack files to Guitar Lab</h2>
<p>Choose the downloaded zip files (you can pick several). Keep this page open until every bar says done.
If it stops, choose the same file again and it carries on where it left off.</p>
<input type="file" id="files" multiple> <button id="go">Upload</button><div id="list"></div>
<script>
const base = location.pathname.replace(/\/upload$/, '');
const CH = 32 * 1024 * 1024;
async function send(file, row) {
  const name = encodeURIComponent(file.name);
  let have = 0;
  try { const r = await fetch(`${base}/size/${name}`); if (r.ok) have = (await r.json()).size; } catch (e) {}
  const bar = row.querySelector('progress'), txt = row.querySelector('span');
  for (let off = have; off < file.size; off += CH) {
    const blob = file.slice(off, Math.min(file.size, off + CH));
    for (let tries = 0; ; tries++) {
      try {
        const r = await fetch(`${base}/up/${name}?offset=${off}`, {method: 'PUT', body: blob});
        if (r.ok) break; throw new Error(r.status);
      } catch (e) { if (tries > 8) { txt.textContent = 'failed, choose the file again to resume'; return; }
        await new Promise(s => setTimeout(s, 3000)); }
    }
    bar.value = (off + blob.size) / file.size; txt.textContent = Math.round(100 * bar.value) + '%';
  }
  await fetch(`${base}/done/${name}?size=${file.size}`, {method: 'POST'});
  bar.value = 1; txt.textContent = 'done';
}
document.getElementById('go').onclick = async () => {
  const list = document.getElementById('list'); list.innerHTML = '';
  const files = [...document.getElementById('files').files];
  const rows = files.map(f => { const d = document.createElement('div'); d.className = 'f';
    d.innerHTML = `<div>${f.name} (${(f.size/1e6).toFixed(0)} MB)</div><progress max="1" value="0"></progress> <span>waiting</span>`;
    list.appendChild(d); return d; });
  for (let i = 0; i < files.length; i++) await send(files[i], rows[i]);
};
</script></body></html>'''

class H(http.server.BaseHTTPRequestHandler):
    def _route(self):
        u = urllib.parse.urlparse(self.path)
        parts = u.path.lstrip('/').split('/', 2)
        if not parts or parts[0] != TOKEN:
            return None, None, None
        q = urllib.parse.parse_qs(u.query)
        return (parts[1] if len(parts) > 1 else ''), (urllib.parse.unquote(parts[2]) if len(parts) > 2 else ''), q
    def _send(self, code, body=b'', ctype='text/plain'):
        self.send_response(code); self.send_header('Content-Type', ctype); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        kind, name, q = self._route()
        if kind is None: return self._send(404)
        if kind == 'upload': return self._send(200, PAGE.encode(), 'text/html; charset=utf-8')
        if kind == 'size':
            p = os.path.join(ROOT, 'up', os.path.basename(name))
            return self._send(200, json.dumps({'size': os.path.getsize(p) if os.path.isfile(p) else 0}).encode(), 'application/json')
        p = os.path.join(ROOT, kind, name) if name else os.path.join(ROOT, kind)
        if '..' in p or not os.path.isfile(p): return self._send(404)
        self.send_response(200); self.send_header('Content-Length', str(os.path.getsize(p))); self.end_headers()
        with open(p, 'rb') as f:
            while True:
                b = f.read(1 << 20)
                if not b: break
                self.wfile.write(b)
    def do_PUT(self):
        kind, name, q = self._route()
        if kind != 'up' or not name: return self._send(403)
        p = os.path.join(ROOT, 'up', os.path.basename(name))
        off = int(q.get('offset', ['0'])[0]); n = int(self.headers['Content-Length'])
        mode = 'r+b' if os.path.exists(p) else 'wb'
        with open(p, mode) as f:
            f.seek(off)
            while n > 0:
                b = self.rfile.read(min(n, 1 << 20)); f.write(b); n -= len(b)
            f.truncate()
        self._send(201)
    def do_POST(self):
        kind, name, q = self._route()
        if kind != 'done': return self._send(403)
        with open(os.path.join(ROOT, 'up', 'DONE.txt'), 'a') as f:
            f.write(f"{os.path.basename(name)} {q.get('size', ['?'])[0]}\n")
        self._send(200)
    def log_message(self, *a): pass
os.makedirs(os.path.join(ROOT, 'up'), exist_ok=True)
http.server.ThreadingHTTPServer(('0.0.0.0', 8000), H).serve_forever()
