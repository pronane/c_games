#!/usr/bin/env node
// The sim must stay near 60 fps of wall time, on a fast link and through a
// delaying proxy. A full 99 s round is the same clock: timer seconds track
// wall seconds, so 99 s of timer is ~99 s of wall time.

import { createRequire } from 'module';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import net from 'net';
import WebSocket from 'ws';
import { createMatch, neutralInput, cloneInput } from './public/sim.mjs';
import { createPacer, stepBudget, redundantBatch, chooseDelay, FRAME_MS, MAX_DELAY_FRAMES } from './public/pace.mjs';

const require = createRequire(import.meta.url);
const { createServer } = require('./server.js');
const here = dirname(fileURLToPath(import.meta.url));
const meta = JSON.parse(readFileSync(join(here, 'public/assets_hd/meta.json'), 'utf8'));
const SECONDS = Number(process.env.PACE_SECONDS || 4);

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }
function check(cond, msg) { if (!cond) throw new Error(msg); }

function mulberry(seed) {
  let a = seed >>> 0;
  return function rand() {
    a |= 0;
    a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function startProxy(targetPort, { delayMs = 0, loss = 0, jitterMs = 0 }) {
  const rnd = mulberry(99);
  return new Promise((resolve) => {
    const server = net.createServer((socket) => {
      const up = net.connect(targetPort, '127.0.0.1');
      const born = Date.now();
      const pipe = (from, to) => {
        let nextAt = 0;
        from.on('data', (chunk) => {
          const extra = loss && Date.now() - born > 500 && rnd() < loss ? 40 : 0;
          const swing = jitterMs ? Math.round((rnd() * 2 - 1) * jitterMs) : 0;
          const now = Date.now();
          const at = Math.max(now + delayMs + swing + extra, nextAt);
          nextAt = at;
          setTimeout(() => { try { to.write(chunk); } catch {} }, Math.max(0, at - now));
        });
        from.on('end', () => { try { to.end(); } catch {} });
        from.on('error', () => { try { to.destroy(); } catch {} });
        from.on('close', () => { try { to.end(); } catch {} });
      };
      pipe(socket, up);
      pipe(up, socket);
    });
    server.listen(0, '127.0.0.1', () => resolve({ server, port: server.address().port }));
  });
}

class Fighter {
  constructor(port, userId, slot, seed) {
    this.userId = userId;
    this.slot = slot;
    this.sim = null;
    this.seed = seed;
    this.msgs = [];
    this.closed = false;
    this.sent = 0;
    this.log = [];
    this.sentFrames = new Set();
    this.peerAck = -1;
    this.remoteMax = -1;
    this.ws = new WebSocket(`ws://127.0.0.1:${port}`);
    this.ws.on('message', (buf) => {
      try { this.msgs.push(JSON.parse(buf.toString())); } catch {}
    });
    this.ws.on('close', () => { this.closed = true; });
    this.ready = new Promise((resolve, reject) => {
      this.ws.once('open', () => resolve());
      this.ws.once('error', reject);
    });
  }
  send(o) { this.ws.send(JSON.stringify(Object.assign({ userId: this.userId }, o))); }
  async wait(pred, ms = 4000) {
    const t0 = Date.now();
    for (;;) {
      const i = this.msgs.findIndex(pred);
      if (i >= 0) return this.msgs.splice(i, 1)[0];
      if (Date.now() - t0 > ms) throw new Error('timeout ' + this.userId);
      await sleep(5);
    }
  }
  arm(seed, delay) {
    this.sim = createMatch({
      p0: 'kairo', p1: 'lyra', seed, delay, frames: meta.characters,
    });
    this.pacer = createPacer(Date.now());
    const inp = neutralInput();
    inp.right = this.slot === 0;
    inp.left = this.slot === 1;
    for (let f = 0; f < delay; f++) this.commit(f, inp);
    this.flush();
  }
  commit(frame, inp) {
    if (this.sentFrames.has(frame)) return;
    if (!this.sim.setInput(this.slot, frame, inp)) return;
    this.sentFrames.add(frame);
    this.log.push({ frame, inp: cloneInput(inp) });
    if (this.log.length > 90) this.log.splice(0, this.log.length - 90);
  }
  flush() {
    const batch = redundantBatch(this.log, this.peerAck);
    if (!batch.length) return;
    this.send({ t: 'input', ack: this.remoteMax, batch });
    this.sent += 1;
  }
  takeMessages(dropRand) {
    const incoming = this.msgs.splice(0);
    for (const m of incoming) {
      if (m.t !== 'input') continue;
      if (dropRand && dropRand() < 0.3) continue;
      if (typeof m.ack === 'number') this.peerAck = Math.max(this.peerAck, m.ack);
      const from = m.from;
      const items = Array.isArray(m.batch) ? m.batch : [];
      for (const item of items) {
        if (!item || typeof item.frame !== 'number') continue;
        this.sim.setInput(from, item.frame, item.inp);
        if (item.frame > this.remoteMax) this.remoteMax = item.frame;
      }
    }
  }
  tick(now, rand) {
    this.takeMessages(null);
    const budget = stepBudget(this.pacer, this.sim.frame, now);
    let steps = 0;
    while (steps < budget && this.sim.canStep() && !this.sim.result) {
      this.sim.step();
      steps += 1;
      const inp = neutralInput();
      if (rand() < 0.5) { inp.right = this.slot === 0; inp.left = this.slot === 1; }
      else { inp.left = this.slot === 0; inp.right = this.slot === 1; }
      if (rand() < 0.02) inp.lp = true;
      this.commit(this.sim.frame - 1 + this.sim.delay, inp);
    }
    if (steps > 0 || now - (this.lastSend || 0) > 120) {
      this.flush();
      this.lastSend = now;
    }
    return steps;
  }
}

async function pair(port, net) {
  const rtt = typeof net === 'number' ? net : net.rtt;
  const jitter = typeof net === 'number' ? (rtt > 200 ? 60 : 8) : net.jitter;
  const samples = typeof net === 'number' ? 8 : (net.samples == null ? 8 : net.samples);
  const a = new Fighter(port, 'pace-a-' + rtt + '-' + Math.random(), 0, 1);
  const b = new Fighter(port, 'pace-b-' + rtt + '-' + Math.random(), 1, 1);
  await a.ready;
  await b.ready;
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
  a.send({ t: 'loaded', startId: cdA.startId, epoch: cdA.epoch, rtt, jitter, samples });
  b.send({ t: 'loaded', startId: cdB.startId, epoch: cdB.epoch, rtt, jitter, samples });
  const go = await a.wait((m) => m.t === 'go', 8000);
  await b.wait((m) => m.t === 'go' && m.startId === go.startId, 8000);
  check(go.delay >= 2 && go.delay <= MAX_DELAY_FRAMES, 'delay out of range ' + go.delay);
  check(go.delay === chooseDelay({ rtt, jitter, samples }, { rtt, jitter, samples }), 'server delay ' + go.delay);
  a.arm(go.seed, go.delay);
  b.arm(go.seed, go.delay);
  a.msgs.length = 0;
  b.msgs.length = 0;
  return { a, b, delay: go.delay };
}

async function runTicks(a, b, ms, hz) {
  const randA = mulberry(3);
  const randB = mulberry(4);
  const step = 1000 / hz;
  // The first inputs are still in flight. That fill is a one-time wait, not
  // the speed of the round, so the fps window starts after it.
  const warmUntil = Date.now() + 1000;
  while (Date.now() < warmUntil) {
    const now = Date.now();
    a.tick(now, randA);
    b.tick(now, randB);
    const left = step - (Date.now() - now);
    if (left > 0) await sleep(left);
  }
  const t0 = Date.now();
  const startFrame = a.sim.frame;
  const startTimer = a.sim.timer;
  const sentAtStart = a.sent;
  let now = t0;
  while (Date.now() - t0 < ms) {
    now = Date.now();
    a.tick(now, randA);
    b.tick(now, randB);
    const left = step - (Date.now() - now);
    if (left > 0) await sleep(left);
  }
  const elapsed = (Date.now() - t0) / 1000;
  const frames = a.sim.frame - startFrame;
  const settleUntil = Date.now() + 800;
  while (Date.now() < settleUntil && a.sim.frame !== b.sim.frame) {
    const now = Date.now();
    a.tick(now, randA);
    b.tick(now, randB);
    await sleep(1000 / 60);
  }
  return {
    fps: frames / elapsed,
    frames,
    elapsed,
    timer: a.sim.timer,
    timerDrop: startTimer - a.sim.timer,
    packetsPerSec: ((a.sent - sentAtStart) / elapsed),
    hashMatch: a.sim.hash() === b.sim.hash() && a.sim.frame === b.sim.frame,
    frameA: a.sim.frame,
    frameB: b.sim.frame,
    hashA: a.sim.hash(),
    hashB: b.sim.hash(),
    delay: a.sim.delay,
  };
}

function assertFps(row, lo, hi) {
  check(row.fps >= lo && row.fps <= hi, `fps ${row.fps.toFixed(2)} not in ${lo}-${hi}`);
  check(row.hashMatch, `hashes diverged frames ${row.frameA}/${row.frameB} hash ${row.hashA}/${row.hashB}`);
  const projected = 99 * (60 / row.fps);
  check(projected > 94 && projected < 104, `99s round would take ${projected.toFixed(1)}s`);
}

async function main() {
  // Virtual clock: 144 Hz renders still produce 60 sim frames per second.
  {
    const pacer = createPacer(0);
    let frame = 0;
    const dt = 1000 / 144;
    for (let i = 1; i <= 1440; i++) {
      frame += stepBudget(pacer, frame, i * dt);
    }
    const fps = frame / 10;
    check(fps > 58 && fps < 62, '144Hz virtual fps ' + fps);
  }

  const srv = createServer();
  const port = await srv.listen(0, '127.0.0.1');
  const summary = [];
  try {
    {
      const { a, b } = await pair(port, 16);
      const row = await runTicks(a, b, SECONDS * 1000, 60);
      assertFps(row, 58, 62);
      check(Math.abs(row.timerDrop - row.elapsed) < 1.5, `timer dropped ${row.timerDrop}s in ${row.elapsed.toFixed(2)}s`);
      summary.push({ name: 'no latency 60Hz', ...row });
      a.ws.close(); b.ws.close();
    }
    {
      const { a, b } = await pair(port, 16);
      const row = await runTicks(a, b, SECONDS * 1000, 144);
      assertFps(row, 58, 62);
      check(row.packetsPerSec < 80, 'sent ' + row.packetsPerSec.toFixed(1) + '/s at 144Hz');
      summary.push({ name: 'no latency 144Hz ticker', packetsPerSec: row.packetsPerSec, fps: row.fps });
      a.ws.close(); b.ws.close();
    }
    {
      // 25 ms on each TCP leg. Ping RTT is ~50 ms; A→B is ~50 ms.
      const proxy = await startProxy(port, { delayMs: 25, loss: 0.01 });
      const { a, b, delay } = await pair(proxy.port, { rtt: 50, jitter: 16, samples: 8 });
      const row = await runTicks(a, b, SECONDS * 1000, 60);
      assertFps(row, 58, 62);
      check(delay >= 2 && delay <= 8, '25ms delay ' + delay);
      summary.push({ name: '25ms+1%', ...row, delay });
      a.ws.close(); b.ws.close();
      proxy.server.close();
    }
    {
      // 120 ms on each TCP leg. Ping RTT is ~240 ms and A→B is ~240 ms,
      // so the delay has to cover a full RTT, not half of one. 5% of chunks
      // are held an extra 40 ms.
      const proxy = await startProxy(port, { delayMs: 120, loss: 0.05 });
      const { a, b, delay } = await pair(proxy.port, { rtt: 240, jitter: 80, samples: 8 });
      const row = await runTicks(a, b, Math.max(SECONDS, 8) * 1000, 60);
      assertFps(row, 58, 62);
      check(delay >= 18 && delay < MAX_DELAY_FRAMES, '120ms delay hit the cap ' + delay);
      summary.push({ name: '120ms+5%', ...row, delay });
      a.ws.close(); b.ws.close();
      proxy.server.close();
    }
    {
      // Same hop, but each chunk also swings ±30 ms, which is the profile
      // that previously landed around 45–50 fps.
      const proxy = await startProxy(port, { delayMs: 120, loss: 0.05, jitterMs: 30 });
      const { a, b, delay } = await pair(proxy.port, { rtt: 240, jitter: 120, samples: 8 });
      const row = await runTicks(a, b, 8000, 60);
      assertFps(row, 58, 62);
      check(delay < MAX_DELAY_FRAMES, '120±30 delay cap ' + delay);
      summary.push({ name: '120ms±30+5%', ...row, delay });
      a.ws.close(); b.ws.close();
      proxy.server.close();
    }
    console.log(JSON.stringify({ ok: true, summary }, null, 2));
  } finally {
    await srv.close();
  }
}

main().catch((err) => {
  console.error('FAIL', err && err.stack || err);
  process.exit(1);
});
