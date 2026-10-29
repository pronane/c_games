#!/usr/bin/env node
'use strict';

// Spins up the multiplayer server and checks the fight can actually start.
//   node test_handshake.js
//   SOAK_SECONDS=60 node test_handshake.js   (default 60)
//
// Cases:
//   1. two clients join, ready, countdown, loaded, go
//   2. a client rejoins mid-way (old socket must not evict the new one)
//   3. 100 sequential pair joins
//   4. input at 60/s is not dropped for SOAK_SECONDS

const WebSocket = require('ws');
const { createServer } = require('./server');

const SOAK_SECONDS = Number(process.env.SOAK_SECONDS || 60);
const CODE_RE = /^[ABCDEFGHJKLMNPQRSTUVWXYZ23456789]{5}$/;

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
    this.closeCode = null;
    this.ws = new WebSocket(`ws://127.0.0.1:${port}`);
    this.ws.on('message', (buf) => {
      try { this.msgs.push(JSON.parse(buf.toString())); } catch {}
    });
    this.ws.on('close', (code) => {
      this.closed = true;
      this.closeCode = code;
    });
    this.ready = new Promise((resolve, reject) => {
      this.ws.once('open', () => resolve(this));
      this.ws.once('error', reject);
    });
  }
  send(o) {
    this.ws.send(JSON.stringify(Object.assign({ userId: this.userId }, o)));
  }
  async wait(pred, ms = 4000) {
    const t0 = Date.now();
    for (;;) {
      const i = this.msgs.findIndex(pred);
      if (i >= 0) return this.msgs.splice(i, 1)[0];
      if (this.closed) throw new Error(`socket closed (${this.closeCode}) while waiting`);
      if (Date.now() - t0 > ms) {
        const tail = this.msgs.slice(-8).map((m) => m.t + (m.msg ? ':' + m.msg : '')).join(',');
        throw new Error(`timeout; recent=[${tail}]`);
      }
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

async function bot(port, userId) {
  const b = new Bot(port, userId);
  await b.ready;
  return b;
}

async function fightUntilGo(a, b) {
  a.send({ t: 'pick', char: 'kairo' });
  b.send({ t: 'pick', char: 'lyra' });
  await a.wait((m) => m.t === 'room_state' && field(m.picks, 0) === 'kairo' && field(m.picks, 1) === 'lyra');
  await b.wait((m) => m.t === 'room_state' && field(m.picks, 0) === 'kairo' && field(m.picks, 1) === 'lyra');
  a.send({ t: 'ready', ready: true, readySeq: 1 });
  a.send({ t: 'ready', ready: true, readySeq: 2 });
  b.send({ t: 'ready', ready: true, readySeq: 1 });
  const cdA = await a.wait((m) => m.t === 'countdown');
  const cdB = await b.wait((m) => m.t === 'countdown');
  check(cdA.startId && cdA.startId === cdB.startId, 'countdown startId mismatch');
  check(cdA.seed === cdB.seed, 'countdown seed mismatch');
  check(cdA.startAt === cdB.startAt, 'countdown startAt mismatch');
  check(typeof cdA.seed === 'number' && cdA.seed > 0, 'seed missing');
  await sleep(40);
  check(!a.msgs.some((m) => m.t === 'go'), 'go arrived before loaded');
  check(!b.msgs.some((m) => m.t === 'go'), 'go arrived before loaded');
  // Stale ready must not cancel the countdown (lower seq, then a wrong epoch).
  a.send({ t: 'ready', ready: false, readySeq: 1, epoch: cdA.epoch });
  a.send({ t: 'ready', ready: false, readySeq: 99, epoch: cdA.epoch - 1 });
  await sleep(80);
  check(!a.msgs.some((m) => m.t === 'countdown_cancel'), 'stale ready cancelled the countdown');
  a.send({ t: 'loaded', startId: cdA.startId, epoch: cdA.epoch });
  await sleep(40);
  check(!a.msgs.some((m) => m.t === 'go'), 'go arrived after only one loaded');
  b.send({ t: 'loaded', startId: cdB.startId, epoch: cdB.epoch });
  const goA = await a.wait((m) => m.t === 'go');
  const goB = await b.wait((m) => m.t === 'go');
  check(goA.startId === goB.startId && goA.startId === cdA.startId, 'go startId mismatch');
  check(goA.seed === goB.seed && goA.seed === cdA.seed, 'go seed mismatch');
  check(goA.startAt === goB.startAt, 'go startAt mismatch');
  check(!a.closed && !b.closed, 'socket closed during handshake');
  return { cdA, goA };
}

async function testHandshake(port) {
  const a = await bot(port, 'user-a');
  const b = await bot(port, 'user-b');
  a.send({ t: 'create' });
  const created = await a.wait((m) => m.t === 'created');
  check(created.slot === 0, 'host slot ' + created.slot);
  check(CODE_RE.test(created.room), 'bad room code ' + created.room);
  check(!/^R\d+$/.test(created.room), 'room code is still sequential');
  b.send({ t: 'join', room: created.room });
  const joined = await b.wait((m) => m.t === 'joined' || m.t === 'error');
  check(joined.t === 'joined', 'join failed: ' + (joined.msg || joined.t));
  check(joined.slot === 1, 'guest got slot ' + joined.slot);
  const { goA } = await fightUntilGo(a, b);
  a.ws.close();
  const left = await b.wait((m) => m.t === 'room_state' && m.phase === 'lobby' && m.started === false && m.seq > goA.seq);
  check(left.started === false, 'started was not reset when a player left');
  check(!field(left.occupied, 0), 'leaver still occupied');
  await Promise.all([a.close(), b.close()]);
  return { room: created.room, startId: goA.startId, seed: goA.seed, startAt: goA.startAt };
}

async function testRejoin(port) {
  const a1 = await bot(port, 'rejoin-user');
  const b = await bot(port, 'rejoin-peer');
  a1.send({ t: 'create' });
  const created = await a1.wait((m) => m.t === 'created');
  b.send({ t: 'join', room: created.room });
  const jb = await b.wait((m) => m.t === 'joined' || m.t === 'error');
  check(jb.t === 'joined' && jb.slot === 1, 'peer did not get slot 1');
  a1.send({ t: 'pick', char: 'kairo' });
  b.send({ t: 'pick', char: 'lyra' });
  await b.wait((m) => m.t === 'room_state' && field(m.picks, 0) === 'kairo' && field(m.picks, 1) === 'lyra');
  a1.send({ t: 'ready', ready: true, readySeq: 1 });
  await b.wait((m) => m.t === 'room_state' && field(m.ready, 0) === true);

  const a2 = await bot(port, 'rejoin-user');
  a2.send({ t: 'join', room: created.room });
  const rejoined = await a2.wait((m) => m.t === 'joined' || m.t === 'error');
  check(rejoined.t === 'joined', 'rejoin failed: ' + (rejoined.msg || ''));
  check(rejoined.rejoin === true, 'rejoin flag missing');
  check(rejoined.slot === 0, 'rejoin slot ' + rejoined.slot);
  check(field(rejoined.ready, 0) === true, 'ready was cleared on replace');
  await a1.close();
  await sleep(200);
  check(!a2.closed, 'new socket closed when the old one closed');
  check(a2.closeCode == null, 'new socket close code ' + a2.closeCode);

  b.send({ t: 'ready', ready: true, readySeq: 1 });
  const cd2 = await a2.wait((m) => m.t === 'countdown', 4000);
  const cdB = await b.wait((m) => m.t === 'countdown', 4000);
  check(cd2.startId === cdB.startId, 'rejoined client missed countdown');
  a2.send({ t: 'loaded', startId: cd2.startId, epoch: cd2.epoch });
  b.send({ t: 'loaded', startId: cdB.startId, epoch: cdB.epoch });
  const go2 = await a2.wait((m) => m.t === 'go');
  const goB = await b.wait((m) => m.t === 'go');
  check(go2.startId === goB.startId, 'rejoined client missed go');
  await Promise.all([a2.close(), b.close()]);

  // Create-rejoin must store the socket, or the next player is also slot 0.
  const c1 = await bot(port, 'host-re');
  c1.send({ t: 'create' });
  const first = await c1.wait((m) => m.t === 'created');
  const c2 = await bot(port, 'host-re');
  c2.send({ t: 'create' });
  const second = await c2.wait((m) => m.t === 'created');
  check(second.room === first.room, 'alone host did not reclaim their room');
  check(second.slot === 0, 'reclaim slot ' + second.slot);
  check(second.rejoin === true, 'create rejoin flag missing');
  await c1.close();
  await sleep(200);
  check(!c2.closed, 'reclaimed socket was removed by the old close');
  const guest = await bot(port, 'guest-re');
  guest.send({ t: 'join', room: second.room });
  const gj = await guest.wait((m) => m.t === 'joined' || m.t === 'error');
  check(gj.t === 'joined', 'guest join failed: ' + (gj.msg || ''));
  check(gj.slot === 1, 'guest was given slot ' + gj.slot + ' (host socket was not stored)');
  c2.send({ t: 'pick', char: 'kairo' });
  guest.send({ t: 'pick', char: 'lyra' });
  c2.send({ t: 'ready', ready: true, readySeq: 1 });
  guest.send({ t: 'ready', ready: true, readySeq: 1 });
  const cdC = await c2.wait((m) => m.t === 'countdown');
  const cdG = await guest.wait((m) => m.t === 'countdown');
  check(cdC.startId === cdG.startId, 'stored host socket missed countdown');
  c2.send({ t: 'loaded', startId: cdC.startId, epoch: cdC.epoch });
  guest.send({ t: 'loaded', startId: cdG.startId, epoch: cdG.epoch });
  const goC = await c2.wait((m) => m.t === 'go');
  await guest.wait((m) => m.t === 'go');
  check(goC.seed === cdC.seed, 'seed changed at go');
  await Promise.all([c2.close(), guest.close()]);
  return { room: created.room, createRoom: second.room, guestSlot: gj.slot };
}

async function testPairs(port) {
  const codes = [];
  for (let i = 0; i < 100; i++) {
    const a = await bot(port, 'A' + i);
    const b = await bot(port, 'B' + i);
    try {
      a.send({ t: 'create' });
      const created = await a.wait((m) => m.t === 'created');
      check(CODE_RE.test(created.room), 'pair ' + i + ' bad code ' + created.room);
      b.send({ t: 'join', room: created.room });
      const joined = await b.wait((m) => m.t === 'joined' || m.t === 'error');
      check(joined.t === 'joined' && joined.slot === 1, 'pair ' + i + ' join ' + (joined.msg || joined.slot));
      a.send({ t: 'pick', char: 'kairo' });
      b.send({ t: 'pick', char: 'lyra' });
      a.send({ t: 'ready', ready: true, readySeq: 1 });
      b.send({ t: 'ready', ready: true, readySeq: 1 });
      const cdA = await a.wait((m) => m.t === 'countdown');
      const cdB = await b.wait((m) => m.t === 'countdown');
      check(cdA.startId === cdB.startId, 'pair ' + i + ' countdown mismatch');
      a.send({ t: 'loaded', startId: cdA.startId, epoch: cdA.epoch });
      b.send({ t: 'loaded', startId: cdB.startId, epoch: cdB.epoch });
      const goA = await a.wait((m) => m.t === 'go');
      const goB = await b.wait((m) => m.t === 'go');
      check(goA.startId === goB.startId, 'pair ' + i + ' go mismatch');
      codes.push(created.room);
    } finally {
      await Promise.all([a.close(), b.close()]);
    }
    if ((i + 1) % 25 === 0) console.log(`  pairs ${i + 1}/100`);
  }
  check(new Set(codes).size === 100, 'room codes collided: ' + codes.length + ' unique ' + new Set(codes).size);
  return { pairs: 100, uniqueCodes: new Set(codes).size };
}

async function testInputSoak(port) {
  const total = SOAK_SECONDS * 60;
  const a = await bot(port, 'soak-a');
  const b = await bot(port, 'soak-b');
  a.send({ t: 'create' });
  const created = await a.wait((m) => m.t === 'created');
  b.send({ t: 'join', room: created.room });
  await b.wait((m) => m.t === 'joined');
  a.send({ t: 'pick', char: 'kairo' });
  b.send({ t: 'pick', char: 'lyra' });
  a.send({ t: 'ready', ready: true, readySeq: 1 });
  b.send({ t: 'ready', ready: true, readySeq: 1 });
  const cdA = await a.wait((m) => m.t === 'countdown');
  const cdB = await b.wait((m) => m.t === 'countdown');
  a.send({ t: 'loaded', startId: cdA.startId, epoch: cdA.epoch });
  b.send({ t: 'loaded', startId: cdB.startId, epoch: cdB.epoch });
  await a.wait((m) => m.t === 'go');
  await b.wait((m) => m.t === 'go');
  b.msgs.length = 0;

  const origin = Date.now();
  let burst = 0;
  for (let i = 0; i < total; i++) {
    const target = origin + (i * 1000) / 60;
    const wait = target - Date.now();
    if (wait > 2) {
      await sleep(wait);
      burst = 0;
    } else if (++burst > 20) {
      await sleep(50);
      burst = 0;
    }
    if (a.closed || b.closed) {
      throw new Error(`socket closed during soak at ${i} (a=${a.closeCode} b=${b.closeCode})`);
    }
    a.send({ t: 'input', n: i, seq: i, inp: { left: i % 2 === 0 } });
    if (i > 0 && i % 600 === 0) console.log(`  inputs sent ${i}/${total}`);
  }
  await sleep(500);
  const inputs = b.msgs.filter((m) => m.t === 'input');
  const seen = new Set(inputs.map((m) => m.n));
  let missing = 0;
  for (let i = 0; i < total; i++) if (!seen.has(i)) missing += 1;
  const elapsed = Date.now() - origin;
  check(!a.closed && !b.closed, `sockets closed (a=${a.closeCode} b=${b.closeCode})`);
  check(missing === 0, `dropped ${missing} of ${total} inputs (got ${inputs.length})`);
  await Promise.all([a.close(), b.close()]);
  return { sent: total, received: inputs.length, missing, elapsedMs: elapsed, rate: 60, seconds: SOAK_SECONDS };
}

async function main() {
  const srv = createServer();
  const summary = [];
  let port = null;
  try {
    port = await srv.listen(0, '127.0.0.1');
    console.log('server', port);
    const handshake = await testHandshake(port);
    console.log('PASS handshake', handshake.room, handshake.startId);
    summary.push({ name: 'two clients join, ready, loaded, go', ok: true, detail: handshake });
    const rejoin = await testRejoin(port);
    console.log('PASS rejoin', rejoin.createRoom, 'guest slot', rejoin.guestSlot);
    summary.push({ name: 'rejoin mid-way and create-rejoin slot', ok: true, detail: rejoin });
    const pairs = await testPairs(port);
    console.log('PASS pairs', pairs.uniqueCodes);
    summary.push({ name: '100 sequential pair joins', ok: true, detail: pairs });
    console.log(`input soak ${SOAK_SECONDS}s at 60/s`);
    const soak = await testInputSoak(port);
    console.log('PASS soak', soak);
    summary.push({ name: 'inputs at 60/s not dropped', ok: true, detail: soak });
    console.log(JSON.stringify({ ok: true, summary }, null, 2));
  } catch (err) {
    console.error('FAIL', err && err.stack || err);
    summary.push({ name: 'failed', ok: false, detail: String(err && err.message || err) });
    console.log(JSON.stringify({ ok: false, summary }, null, 2));
    process.exitCode = 1;
  } finally {
    await srv.close();
  }
}

main();
