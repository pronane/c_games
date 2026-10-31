// Run just the Arena FC server (no hub): node arena/standalone.js --port 7777
// Same HTTP surface as the .NET server: /health (JSON) and a status page at /, WebSocket on any path.
'use strict';
const http = require('http');
const { createArenaServer } = require('./server');

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 && process.argv[i + 1] !== undefined ? process.argv[i + 1] : fallback;
}

function createStandalone(opts = {}) {
  const arena = createArenaServer(opts);
  const server = http.createServer((req, res) => {
    const p = (req.url || '/').split('?')[0];
    if (p === '/health') { res.setHeader('Content-Type', 'application/json'); res.end(JSON.stringify(arena.health())); return; }
    res.setHeader('Content-Type', 'text/plain');
    res.end(`Arena FC server (Node)\nrooms: ${arena.rooms.size}\n`);
  });
  server.on('upgrade', (req, socket, head) => arena.upgrade(req, socket, head));
  return {
    arena, server,
    listen: (port, host) => new Promise((resolve) => server.listen(port, host || '0.0.0.0', () => resolve(server.address().port))),
    close: async () => { await arena.close(); await new Promise((r) => server.close(() => r())); },
  };
}

if (require.main === module) {
  const s = createStandalone({
    halfMinutes: Number(arg('half-minutes', 45)), timeSpeed: Number(arg('time-speed', 15)),
    graceSeconds: Number(arg('grace-seconds', 180)), seed: arg('seed', undefined) === undefined ? undefined : Number(arg('seed')),
  });
  s.listen(Number(arg('port', process.env.PORT || 7777)), arg('bind', '0.0.0.0')).then((p) => console.log(`Arena FC (Node) listening on ws://0.0.0.0:${p}`));
}

module.exports = { createStandalone };
