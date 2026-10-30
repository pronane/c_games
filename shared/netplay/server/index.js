// HTTP + WebSocket front for one or more lockstep relays (relay.js).
//
//   createServer(game, opts)  one game: every WebSocket path goes to it.
//   createHub(games, opts)    several games on one port, picked by path,
//                             e.g. '/' HD Fighter, '/egyptian', '/turbo'.
//
// opts.static: [{ route: '/', dir }, { route: '/assets', dir }] served with no caching.
const express = require('express');
const http = require('http');
const { createRelay } = require('./relay');

function noStore(res) {
  res.setHeader('Cache-Control', 'no-store');
}

function mountStatic(app, list) {
  for (const s of list || []) {
    app.use(s.route || '/', express.static(s.dir, { etag: false, maxAge: 0, setHeaders: noStore }));
  }
}

function pathOf(req) {
  const url = req.url || '/';
  const q = url.indexOf('?');
  const p = q === -1 ? url : url.slice(0, q);
  return p.length > 1 && p.endsWith('/') ? p.slice(0, -1) : p;
}

// entries: [{ path, relay }]. An exact path wins; otherwise the '/' entry takes it.
function routeUpgrades(server, entries) {
  server.on('upgrade', (req, socket, head) => {
    const p = pathOf(req);
    const hit = entries.find((e) => e.path === p) || entries.find((e) => e.path === '/');
    if (!hit) {
      socket.destroy();
      return;
    }
    hit.relay.wss.handleUpgrade(req, socket, head, (ws) => hit.relay.wss.emit('connection', ws, req));
  });
}

function listenOn(server) {
  return (port, host) => new Promise((resolve, reject) => {
    const onError = (err) => reject(err);
    server.once('error', onError);
    server.listen(port, host || '0.0.0.0', () => {
      server.removeListener('error', onError);
      resolve(server.address().port);
    });
  });
}

function closer(server, relays) {
  return async () => {
    await Promise.all(relays.map((r) => r.close()));
    if (server.listening) await new Promise((resolve) => server.close(() => resolve()));
  };
}

function createServer(game = {}, opts = {}) {
  const app = express();
  const server = http.createServer(app);
  const relay = createRelay(game);
  mountStatic(app, opts.static);
  routeUpgrades(server, [{ path: '/', relay }]);
  app.get('/api/rooms', (req, res) => res.json(relay.roomList()));
  app.get('/api/health', (req, res) => res.json(relay.health()));
  return { listen: listenOn(server), close: closer(server, [relay]), app, server, relay };
}

// games: [{ path: '/egyptian', game: {...}, static: [...] }]
function createHub(games, opts = {}) {
  const app = express();
  const server = http.createServer(app);
  const entries = games.map((g) => ({
    path: g.path || '/',
    relay: createRelay(Object.assign({ logPrefix: games.length > 1 }, g.game)),
    static: g.static,
  }));
  for (const e of entries) {
    const base = e.path === '/' ? '' : e.path;
    for (const s of e.static || []) mountStatic(app, [{ route: base + (s.route === '/' ? '' : s.route || '') || '/', dir: s.dir }]);
    app.get(`${base}/api/rooms`, (req, res) => res.json(e.relay.roomList()));
    app.get(`${base}/api/health`, (req, res) => res.json(e.relay.health()));
  }
  mountStatic(app, opts.static);
  if (!entries.some((e) => e.path === '/')) {
    app.get('/api/health', (req, res) => res.json({
      ok: true,
      protocol: 2,
      games: entries.map((e) => Object.assign({ path: e.path }, e.relay.health())),
    }));
  }
  routeUpgrades(server, entries);
  return { listen: listenOn(server), close: closer(server, entries.map((e) => e.relay)), app, server, relays: entries };
}

module.exports = { createServer, createHub, createRelay };
