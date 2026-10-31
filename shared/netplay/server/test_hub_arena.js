// Hub + Arena FC proxy: routing, health, and a WebSocket round trip through /arena/ws.
// Starts a fake "Arena FC server" so no .NET is needed:  node test_hub_arena.js
const assert = require('assert');
const http = require('http');
const WebSocket = require('ws');

function get(port, path) {
  return new Promise((resolve, reject) => {
    http.get({ host: '127.0.0.1', port, path }, (res) => {
      let body = '';
      res.on('data', (d) => { body += d; });
      res.on('end', () => resolve({ status: res.statusCode, body }));
    }).on('error', reject);
  });
}

(async () => {
  const fake = new WebSocket.Server({ port: 0, host: '127.0.0.1' });
  await new Promise((r) => fake.once('listening', r));
  fake.on('connection', (s) => {
    s.send(JSON.stringify({ t: 'welcome', ver: 2 }));
    s.on('message', (d) => s.send(d.toString()));
  });
  const backendPort = fake.address().port;

  // games.js reads these when it loads, so set them first.
  process.env.ARENA_BACKEND = `ws://127.0.0.1:${backendPort}`;
  process.env.ARENA_WEB_DIR = __dirname;                    // any directory: only used for static files
  const { createHub } = require('./index');
  const { hubGames } = require('./games');
  assert.ok(hubGames.some((g) => g.path === '/arena'), 'arena entry present when ARENA_BACKEND is set');

  const quiet = hubGames.map((g) => (g.proxy ? Object.assign({}, g, { proxy: Object.assign({ quiet: true, pingMs: 0 }, g.proxy) })
    : Object.assign({}, g, { game: Object.assign({ quiet: true }, g.game) })));
  const hub = createHub(quiet);
  const port = await hub.listen(0, '127.0.0.1');
  try {
    // existing games keep their routes
    assert.strictEqual(JSON.parse((await get(port, '/api/health')).body).game, 'hd-fighter');
    assert.strictEqual(JSON.parse((await get(port, '/egyptian/api/health')).body).game, 'egyptian-fighter');
    assert.strictEqual(JSON.parse((await get(port, '/turbo/api/health')).body).game, 'turbotumble64');

    // arena health follows the backend
    const up = await get(port, '/arena/api/health');
    assert.strictEqual(up.status, 200);
    assert.strictEqual(JSON.parse(up.body).backend, 'up');

    // a plain GET of the socket path is refused, not proxied
    assert.strictEqual((await get(port, '/arena/ws')).status, 426);

    // WebSocket through the hub reaches the fake server and back
    const ws = new WebSocket(`ws://127.0.0.1:${port}/arena/ws`);
    const got = [];
    ws.on('message', (d) => got.push(JSON.parse(d.toString())));
    await new Promise((r) => ws.once('open', r));
    ws.send(JSON.stringify({ t: 'hello', name: 'Sam' }));
    await new Promise((r) => setTimeout(r, 300));
    assert.strictEqual(got[0].t, 'welcome');
    assert.strictEqual(got[1].name, 'Sam');
    ws.close();

    // the fighters' relay is still reachable on its own path
    const f = new WebSocket(`ws://127.0.0.1:${port}/egyptian`);
    await new Promise((r, j) => { f.once('open', r); f.once('error', j); });
    f.close();

    // backend goes away -> health 503
    for (const c of fake.clients) c.terminate();
    await new Promise((r) => fake.close(r));
    assert.strictEqual((await get(port, '/arena/api/health')).status, 503);
    console.log('hub arena: ok');
  } finally {
    await hub.close();
  }
  process.exit(0);
})().catch((e) => { console.error(e); process.exit(1); });
