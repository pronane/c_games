// Hub routing: each game path has its own rooms; health per path.
const assert = require('assert');
const http = require('http');
const WebSocket = require('ws');
const { createHub } = require('./index');
const { hubGames } = require('./games');

function getJson(port, path) {
  return new Promise((resolve, reject) => {
    http.get({ host: '127.0.0.1', port, path }, (res) => {
      let body = '';
      res.on('data', (d) => { body += d; });
      res.on('end', () => { try { resolve(JSON.parse(body)); } catch (e) { reject(e); } });
    }).on('error', reject);
  });
}

function ask(port, path, msg, want) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`ws://127.0.0.1:${port}${path}`);
    const timer = setTimeout(() => reject(new Error(`no ${want} on ${path}`)), 3000);
    ws.on('open', () => ws.send(JSON.stringify(msg)));
    ws.on('message', (raw) => {
      const m = JSON.parse(raw);
      if (m.t !== want) return;
      clearTimeout(timer);
      ws.close();
      resolve(m);
    });
    ws.on('error', reject);
  });
}

(async () => {
  const hub = createHub(hubGames.map((g) => Object.assign({}, g, { game: Object.assign({ quiet: true }, g.game) })));
  const port = await hub.listen(0, '127.0.0.1');
  try {
    assert.strictEqual((await getJson(port, '/api/health')).game, 'hd-fighter');
    assert.strictEqual((await getJson(port, '/egyptian/api/health')).game, 'egyptian-fighter');
    assert.strictEqual((await getJson(port, '/turbo/api/health')).game, 'turbotumble64');

    const created = await ask(port, '/egyptian', { t: 'create', userId: 'hub-a' }, 'created');
    assert.match(created.room, /^[A-Z0-9]{5}$/);
    const wrongGame = await ask(port, '/turbo', { t: 'join', room: created.room, userId: 'hub-b' }, 'error');
    assert.strictEqual(wrongGame.msg, 'Room not found');
    const hd = await ask(port, '/', { t: 'create', userId: 'hub-c' }, 'created');
    assert.notStrictEqual(hd.room, undefined);
    const badPick = await ask(port, '/egyptian', { t: 'create', userId: 'hub-d', char: '9' }, 'created');
    assert.strictEqual(badPick.picks[0], null);
    console.log('PASS hub routing', created.room, hd.room);
  } finally {
    await hub.close();
  }
})().catch((err) => {
  console.error('FAIL', err);
  process.exit(1);
});
