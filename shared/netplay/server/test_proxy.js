// Tests for proxy.js against a fake backend. Needs only `ws`:  node test_proxy.js
const http = require('http');
const WebSocket = require('ws');
const { createWsProxy } = require('./proxy');

let failed = 0;
function ok(cond, msg) {
  console.log((cond ? 'PASS ' : 'FAIL ') + msg);
  if (!cond) failed++;
}
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
function listen(server) {
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server.address().port)));
}
function open(url, opts) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url, opts);
    ws.once('open', () => resolve(ws));
    ws.once('error', reject);
    ws.once('unexpected-response', (_req, res) => reject(Object.assign(new Error('http ' + res.statusCode), { status: res.statusCode })));
  });
}
function next(ws) {
  return new Promise((resolve) => ws.once('message', (d, bin) => resolve({ data: d, bin })));
}
function closed(ws) {
  return new Promise((resolve) => ws.once('close', (code) => resolve(code)));
}

async function main() {
  // ---- fake backend: echoes frames, greets, and records what it saw
  const seen = { headers: null, count: 0 };
  const backendWss = new WebSocket.Server({ port: 0, host: '127.0.0.1' });
  await new Promise((r) => backendWss.once('listening', r));
  const backendPort = backendWss.address().port;
  let backendSockets = [];
  backendWss.on('connection', (s, req) => {
    seen.headers = req.headers;
    seen.count++;
    backendSockets.push(s);
    s.send(JSON.stringify({ t: 'welcome' }));
    s.on('message', (d, bin) => s.send(d, { binary: bin }));
  });

  const proxy = createWsProxy({ target: `ws://127.0.0.1:${backendPort}`, quiet: true, maxPerIp: 3, allowedOrigins: [], pingMs: 0 });
  const front = http.createServer();
  front.on('upgrade', (req, socket, head) => proxy.upgrade(req, socket, head));
  const port = await listen(front);
  const url = `ws://127.0.0.1:${port}/arena/ws`;

  // ---- text + binary framing is preserved
  const a = await open(url);
  const hello = await next(a);
  ok(!hello.bin && JSON.parse(hello.data.toString()).t === 'welcome', 'backend greeting reaches the client as text');
  a.send(JSON.stringify({ t: 'hello', name: 'Sam' }));
  const echo = await next(a);
  ok(!echo.bin && JSON.parse(echo.data.toString()).name === 'Sam', 'text frame round-trips as text');
  a.send(Buffer.from([1, 2, 3, 250]), { binary: true });
  const bin = await next(a);
  ok(bin.bin && Buffer.compare(bin.data, Buffer.from([1, 2, 3, 250])) === 0, 'binary frame round-trips as binary');
  ok(seen.headers && seen.headers['x-forwarded-for'] === '127.0.0.1', 'backend sees the real client address: ' + (seen.headers && seen.headers['x-forwarded-for']));

  // ---- messages sent before the backend socket finishes opening are queued, in order
  const slowWss = new WebSocket.Server({ noServer: true });
  const slowBackend = http.createServer();
  const slowGot = [];
  slowBackend.on('upgrade', (req, socket, head) => setTimeout(() => slowWss.handleUpgrade(req, socket, head, (s) => {
    s.on('message', (d) => { slowGot.push(d.toString()); });
  }), 200));
  const slowPort = await listen(slowBackend);
  const slowProxy = createWsProxy({ target: `ws://127.0.0.1:${slowPort}`, quiet: true, pingMs: 0 });
  const slowFront = http.createServer();
  slowFront.on('upgrade', (req, socket, head) => slowProxy.upgrade(req, socket, head));
  const slowFrontPort = await listen(slowFront);
  const q = await open(`ws://127.0.0.1:${slowFrontPort}/x`);
  q.send('one'); q.send('two'); q.send('three');
  await wait(600);
  ok(slowGot.join(',') === 'one,two,three', 'early frames queued and delivered in order: ' + slowGot.join(','));
  q.close();

  // ---- close propagates both ways
  const closeBack = closed(a);
  backendSockets[backendSockets.length - 1].close(4001, 'bye');
  const code = await closeBack;
  ok(code === 4001, 'backend close code propagates to the client: ' + code);
  const b = await open(url);
  await next(b);
  const sockB = backendSockets[backendSockets.length - 1];
  const backClosed = closed(sockB);
  b.close(1000, 'done');
  await backClosed;
  ok(true, 'client close closes the backend socket');

  // ---- per-IP cap
  const held = [];
  for (let i = 0; i < 3; i++) held.push(await open(url));
  let status = 0;
  try { await open(url); } catch (e) { status = e.status || 0; }
  ok(status === 429, 'fourth connection from one IP refused with 429: ' + status);
  held.forEach((w) => w.close());
  await wait(100);
  const again = await open(url);
  ok(again.readyState === WebSocket.OPEN, 'slot is freed after clients leave');
  again.close();

  // ---- Origin allow-list
  const strict = createWsProxy({ target: `ws://127.0.0.1:${backendPort}`, quiet: true, allowedOrigins: 'https://good.example', pingMs: 0 });
  const strictFront = http.createServer();
  strictFront.on('upgrade', (req, socket, head) => strict.upgrade(req, socket, head));
  const strictPort = await listen(strictFront);
  let bad = 0;
  try { await open(`ws://127.0.0.1:${strictPort}/`, { origin: 'https://evil.example' }); } catch (e) { bad = e.status || 0; }
  ok(bad === 403, 'wrong Origin refused with 403: ' + bad);
  const good = await open(`ws://127.0.0.1:${strictPort}/`, { origin: 'https://good.example' });
  ok(good.readyState === WebSocket.OPEN, 'allowed Origin accepted');
  good.close();

  // ---- health and a dead backend
  ok(await proxy.health() === true, 'health true while the backend is up');
  const deadProxy = createWsProxy({ target: 'ws://127.0.0.1:1', quiet: true, pingMs: 0 });
  ok(await deadProxy.health() === false, 'health false when nothing listens');
  const deadFront = http.createServer();
  deadFront.on('upgrade', (req, socket, head) => deadProxy.upgrade(req, socket, head));
  const deadPort = await listen(deadFront);
  const d = await open(`ws://127.0.0.1:${deadPort}/`);
  const dcode = await closed(d);
  ok(dcode === 1011, 'client is told 1011 when the game server is down: ' + dcode);

  // ---- oversized frames are refused, not forwarded
  const big = await open(url);
  await next(big);
  const bigClosed = closed(big);
  big.send(Buffer.alloc(2 * 1024 * 1024));
  const bigCode = await bigClosed;
  ok(bigCode === 1009, '2 MB frame closes the socket with 1009: ' + bigCode);

  // ---- clean shutdown
  await proxy.close(); await slowProxy.close(); await strict.close(); await deadProxy.close();
  for (const s of [front, slowFront, strictFront, deadFront, slowBackend]) s.close();
  backendWss.close();
  console.log(failed ? `FAILED ${failed}` : 'ALL PASSED');
  process.exit(failed ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(1); });
