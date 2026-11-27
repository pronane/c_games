// Serve only the production bundle to Electron on the same runner.
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
function createCaptureServer(directory) {
  const root = path.resolve(directory);
  const types = { '.html': 'text/html', '.js': 'application/javascript', '.css': 'text/css',
    '.json': 'application/json', '.glb': 'model/gltf-binary', '.png': 'image/png',
    '.jpg': 'image/jpeg', '.webp': 'image/webp', '.wasm': 'application/wasm' };
  return http.createServer((req, res) => {
    let file;
    try {
      const pathname = decodeURIComponent(new URL(req.url, 'http://capture.invalid').pathname);
      file = path.resolve(root, '.' + (pathname === '/' ? '/index.html' : pathname));
    } catch { res.writeHead(400); return res.end(); }
    if (!file.startsWith(root + path.sep)) { res.writeHead(403); return res.end(); }
    fs.readFile(file, (err, bytes) => {
      if (err) { res.writeHead(404); return res.end(); }
      res.writeHead(200, { 'Content-Type': types[path.extname(file)] ?? 'application/octet-stream', 'Cache-Control': 'no-store' });
      res.end(bytes);
    });
  });
}
module.exports = { createCaptureServer };
