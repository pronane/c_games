// Hub with the in-process Arena FC server (ARENA_NATIVE=1): routes, health, and a lobby round trip on /arena/ws.
const assert = require('assert');
const http = require('http');
const WebSocket = require('ws');
process.env.ARENA_NATIVE = '1';
delete process.env.ARENA_BACKEND;
process.env.ARENA_WEB_DIR = __dirname;
const { createHub } = require('./index');
const { hubGames } = require('./games');

const get = (port, path) => new Promise((resolve, reject) => {
  http.get({ host: '127.0.0.1', port, path }, (res) => { let b = ''; res.on('data', (d) => { b += d; }); res.on('end', () => resolve({ status: res.statusCode, body: b })); }).on('error', reject);
});

(async () => {
  const entry = hubGames.find((g) => g.path === '/arena');
  assert.ok(entry && entry.native, 'native arena entry present when ARENA_NATIVE=1');
  const quiet = hubGames.map((g) => (g.native ? Object.assign({}, g, { native: Object.assign({ quiet: true }, g.native) })
    : g.proxy ? g : Object.assign({}, g, { game: Object.assign({ quiet: true }, g.game) })));
  const hub = createHub(quiet);
  const port = await hub.listen(0, '127.0.0.1');
  try {
    assert.strictEqual(JSON.parse((await get(port, '/api/health')).body).game, 'hd-fighter');
    assert.strictEqual(JSON.parse((await get(port, '/egyptian/api/health')).body).game, 'egyptian-fighter');
    const h = await get(port, '/arena/api/health');
    assert.strictEqual(h.status, 200);
    assert.strictEqual(JSON.parse(h.body).server, 'node');
    assert.strictEqual((await get(port, '/arena/ws')).status, 426);
    const ws = new WebSocket(`ws://127.0.0.1:${port}/arena/ws`);
    const got = [];
    ws.on('message', (d) => got.push(JSON.parse(d.toString())));
    await new Promise((r, j) => { ws.once('open', r); ws.once('error', j); });
    ws.send(JSON.stringify({ t: 'hello', ver: 2, name: 'Sam', room: '', create: true }));
    await new Promise((r) => setTimeout(r, 300));
    const w = got.find((m) => m.t === 'welcome');
    assert.ok(w && w.slot === 0 && w.room.length === 6, 'welcome through the hub');
    assert.ok(got.some((m) => m.t === 'lobby' && m.names[0] === 'Sam'), 'lobby through the hub');
    ws.send(JSON.stringify({ t: 'start' }));
    await new Promise((r) => setTimeout(r, 400));
    assert.ok(got.some((m) => m.t === 'begin') && got.some((m) => m.t === 'snap'), 'match runs through the hub');
    ws.close();
    // the fighters' relay still works on its own path
    const f = new WebSocket(`ws://127.0.0.1:${port}/egyptian`);
    await new Promise((r, j) => { f.once('open', r); f.once('error', j); });
    f.close();
    console.log('hub arena native: ok');
  } finally {
    await hub.close();
  }
  process.exit(0);
})().catch((e) => { console.error(e); process.exit(1); });
