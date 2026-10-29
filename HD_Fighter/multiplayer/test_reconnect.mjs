// Reconnect without re-picking, and a mid-fight drop that can resume or forfeit.
// HOLD_MS is short so the forfeit case does not wait 30 s.

process.env.HOLD_MS = '700';

import { createRequire } from 'module';
import WebSocket from 'ws';
import { createMatch, neutralInput } from './public/sim.mjs';
import { unpackHist, unpackInput, packInput } from './public/wire.mjs';

const require = createRequire(import.meta.url);
const { createServer } = require('./server.js');

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }
function check(cond, msg) { if (!cond) throw new Error(msg); }
function field(obj, i) {
  if (!obj) return undefined;
  return obj[i] != null ? obj[i] : obj[String(i)];
}

class Bot {
  constructor(port, userId) {
    this.userId = userId;
    this.msgs = [];
    this.closed = false;
    this.ws = new WebSocket(`ws://127.0.0.1:${port}`);
    this.ws.on('message', (buf) => {
      try { this.msgs.push(JSON.parse(buf.toString())); } catch {}
    });
    this.ws.on('close', () => { this.closed = true; });
    this.ready = new Promise((resolve, reject) => {
      this.ws.once('open', () => resolve(this));
      this.ws.once('error', reject);
    });
  }
  send(o) { this.ws.send(JSON.stringify(Object.assign({ userId: this.userId }, o))); }
  async wait(pred, ms = 4000) {
    const t0 = Date.now();
    for (;;) {
      const i = this.msgs.findIndex(pred);
      if (i >= 0) return this.msgs.splice(i, 1)[0];
      if (Date.now() - t0 > ms) throw new Error('timeout ' + this.userId + ' ' + (this.msgs.slice(-4).map((m) => m.t).join(',')));
      await sleep(5);
    }
  }
  close() {
    return new Promise((resolve) => {
      if (this.closed) return resolve();
      this.ws.once('close', () => resolve());
      try { this.ws.close(); } catch { resolve(); }
    });
  }
}

async function storm(port) {
  const host = await new Bot(port, 'storm-host').ready;
  host.send({ t: 'create' });
  const created = await host.wait((m) => m.t === 'created');
  const guestId = 'storm-guest';
  let guest = await new Bot(port, guestId).ready;
  guest.send({ t: 'join', room: created.room });
  await guest.wait((m) => m.t === 'joined');
  host.send({ t: 'pick', char: 'kairo' });
  guest.send({ t: 'pick', char: 'lyra' });
  await host.wait((m) => m.t === 'room_state' && field(m.picks, 1) === 'lyra');
  let ok = 0;
  for (let i = 0; i < 300; i++) {
    await guest.close();
    guest = await new Bot(port, guestId).ready;
    guest.send({ t: 'join', room: created.room });
    const joined = await guest.wait((m) => m.t === 'joined' && m.rejoin);
    check(field(joined.picks, 1) === 'lyra', 'pick was not restored on rejoin ' + i);
    guest.send({ t: 'ready', ready: true, readySeq: i + 1 });
    const ack = await guest.wait((m) => m.t === 'ready_ack' || m.t === 'error');
    check(ack.t === 'ready_ack' && ack.ready === true, 'ready without re-pick failed: ' + (ack.msg || ack.t));
    ok += 1;
  }
  await host.close();
  await guest.close();
  return { ok };
}

function feed(sim, slot, m) {
  if (m.t !== 'input') return;
  const items = [];
  if (typeof m.base === 'number' && Array.isArray(m.bits)) {
    for (let i = 0; i < m.bits.length; i++) items.push({ frame: m.base + i, bits: m.bits[i] });
  }
  if (Array.isArray(m.batch)) {
    for (const item of m.batch) {
      if (!item || typeof item.frame !== 'number') continue;
      items.push({ frame: item.frame, bits: typeof item.b === 'number' ? item.b : packInput(item.inp) });
    }
  }
  for (const item of items) {
    if (m.from === slot) continue;
    sim.setInput(m.from, item.frame, unpackInput(item.bits));
  }
}

async function fightPair(port, tag) {
  const a = await new Bot(port, tag + '-a').ready;
  const b = await new Bot(port, tag + '-b').ready;
  a.send({ t: 'create' });
  const created = await a.wait((m) => m.t === 'created');
  b.send({ t: 'join', room: created.room });
  await b.wait((m) => m.t === 'joined');
  a.send({ t: 'pick', char: 'kairo' });
  b.send({ t: 'pick', char: 'lyra' });
  a.send({ t: 'ready', ready: true, readySeq: 1 });
  b.send({ t: 'ready', ready: true, readySeq: 1 });
  const cd = await a.wait((m) => m.t === 'countdown');
  await b.wait((m) => m.t === 'countdown');
  a.send({ t: 'loaded', startId: cd.startId, epoch: cd.epoch, rtt: 20, jitter: 4, samples: 8 });
  b.send({ t: 'loaded', startId: cd.startId, epoch: cd.epoch, rtt: 20, jitter: 4, samples: 8 });
  const go = await a.wait((m) => m.t === 'go');
  await b.wait((m) => m.t === 'go');
  const simA = createMatch({ p0: 'kairo', p1: 'lyra', seed: go.seed, delay: go.delay });
  const simB = createMatch({ p0: 'kairo', p1: 'lyra', seed: go.seed, delay: go.delay });
  const local = [new Map(), new Map()];
  const sendInput = (bot, slot, frame) => {
    const inp = neutralInput();
    inp.right = slot === 0;
    inp.left = slot === 1;
    local[slot].set(frame, inp);
    const bits = packInput(inp);
    bot.send({ t: 'input', base: frame, bits: [bits] });
    (slot === 0 ? simA : simB).setInput(slot, frame, inp);
  };
  for (let f = 0; f < go.delay + 24; f++) {
    sendInput(a, 0, f);
    sendInput(b, 1, f);
  }
  const until = Date.now() + 2000;
  while (Date.now() < until && (simA.frame < 8 || simB.frame < 8)) {
    for (const m of a.msgs.splice(0)) feed(simA, 0, m);
    for (const m of b.msgs.splice(0)) feed(simB, 1, m);
    while (simA.canStep() && simA.frame < 12) simA.step();
    while (simB.canStep() && simB.frame < 12) simB.step();
    await sleep(10);
  }
  check(simA.frame >= 8 && simA.frame === simB.frame, 'sims did not advance ' + simA.frame + '/' + simB.frame);
  check(simA.hash() === simB.hash(), 'pre-drop hash');
  return { a, b, simA, simB, room: created.room, go, local };
}

async function resume(port) {
  const { a, b, simA, room } = await fightPair(port, 'resume');
  const frame = simA.frame;
  const hash = simA.hash() >>> 0;
  await b.close();
  const hold = await a.wait((m) => m.t === 'peer_hold');
  check(hold.slot === 1, 'hold slot');
  a.send({ t: 'hold_frame', frame, hash });
  const b2 = await new Bot(port, 'resume-b').ready;
  b2.send({ t: 'join', room });
  const resumed = await b2.wait((m) => m.t === 'resume', 4000);
  check(resumed.frame === frame, 'resume frame ' + resumed.frame);
  const p0 = unpackHist(resumed.p0);
  const p1 = unpackHist(resumed.p1);
  const fresh = createMatch({ p0: 'kairo', p1: 'lyra', seed: resumed.seed, delay: resumed.delay });
  const end = Math.max(resumed.end | 0, frame);
  for (let f = 0; f < end; f++) {
    fresh.setInput(0, f, unpackInput(p0[f] || 0));
    fresh.setInput(1, f, unpackInput(p1[f] || 0));
  }
  while (fresh.frame < frame && fresh.canStep()) fresh.step();
  check(fresh.frame === frame, 'replay stopped at ' + fresh.frame);
  check((fresh.hash() >>> 0) === hash, 'resume hash ' + fresh.hash() + ' vs ' + hash);
  const back = await a.wait((m) => m.t === 'peer_back');
  check(back.frame === frame, 'peer_back');
  await a.close();
  await b2.close();
  return { frame, hash };
}

async function forfeit(port) {
  const { a, b, room } = await fightPair(port, 'forfeit');
  await b.close();
  await a.wait((m) => m.t === 'peer_hold');
  const msg = await a.wait((m) => m.t === 'forfeit', 3000);
  check(msg.winner === 0 && msg.loser === 1, 'winner ' + msg.winner);
  const state = await a.wait((m) => m.t === 'room_state' && m.phase === 'lobby');
  check(field(state.picks, 0) === 'kairo', 'pick cleared, rematch would need a re-pick');
  check(field(state.ready, 0) === false && state.started === false, 'ready not reset');
  a.send({ t: 'ready', ready: true, readySeq: 2 });
  const ack = await a.wait((m) => m.t === 'ready_ack' || m.t === 'error');
  check(ack.t === 'ready_ack', 'rematch ready failed ' + (ack.msg || ''));
  await a.close();
  return { room, winner: msg.winner };
}

async function main() {
  const srv = createServer();
  const port = await srv.listen(0, '127.0.0.1');
  try {
    const stormed = await storm(port);
    check(stormed.ok === 300, 'storm ' + stormed.ok);
    console.log('PASS storm', stormed.ok);
    const resumed = await resume(port);
    console.log('PASS resume', resumed.frame, resumed.hash);
    const forfeited = await forfeit(port);
    console.log('PASS forfeit', forfeited.room, 'winner', forfeited.winner);
    console.log(JSON.stringify({ ok: true, storm: stormed.ok, resume: resumed, forfeit: forfeited.winner }));
  } finally {
    await srv.close();
  }
}

main().catch((err) => {
  console.error('FAIL', err && err.stack || err);
  process.exit(1);
});
