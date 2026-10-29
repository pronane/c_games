#!/usr/bin/env node
// Two copies of the real sim, inputs carried by the WebSocket relay,
// with per-direction latency and jitter. Hashes must match for 60s (3600 frames).

import { createRequire } from 'module';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
import WebSocket from 'ws';
import { createMatch, neutralInput, cloneInput, HASH_EVERY } from './public/sim.mjs';

const require = createRequire(import.meta.url);
const { createServer } = require('./server.js');
const here = dirname(fileURLToPath(import.meta.url));
const meta = JSON.parse(readFileSync(join(here, 'public/assets_hd/meta.json'), 'utf8'));
const FRAMES = Number(process.env.LOCK_FRAMES || 3600);

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

function randomInput(rand) {
  const inp = neutralInput();
  const roll = rand();
  if (roll < 0.3) inp.left = true;
  else if (roll < 0.6) inp.right = true;
  if (rand() < 0.04) inp.jump = true;
  if (rand() < 0.03) inp.down = true;
  if (rand() < 0.02) inp.lp = true;
  if (rand() < 0.015) inp.hp = true;
  if (rand() < 0.04) inp.block = true;
  return inp;
}

function oneSwingDamage() {
  const sim = createMatch({ p0: 'kairo', p1: 'lyra', seed: 99, delay: 1, frames: meta.characters });
  sim.fighters[0].x = 400;
  sim.fighters[1].x = 470;
  const atk = neutralInput();
  atk.hp = true;
  const idle = neutralInput();
  for (let f = 0; f < 20; f++) {
    sim.setInput(0, f, atk);
    sim.setInput(1, f, idle);
    sim.step();
  }
  return 100 - sim.fighters[1].hp;
}

class Side {
  constructor(port, userId, slot, seed) {
    this.userId = userId;
    this.slot = slot;
    this.sim = createMatch({
      p0: 'kairo',
      p1: 'lyra',
      seed,
      delay: 3,
      frames: meta.characters,
    });
    this.msgs = [];
    this.queue = [];
    this.lane = 0;
    this.closed = false;
    this.ws = new WebSocket(`ws://127.0.0.1:${port}`);
    this.ws.on('message', (buf) => {
      try { this.msgs.push(JSON.parse(buf.toString())); } catch {}
    });
    this.ws.on('close', () => { this.closed = true; });
    this.ready = new Promise((resolve, reject) => {
      this.ws.once('open', resolve);
      this.ws.once('error', reject);
    });
    this.pending = [];
    this.sent = new Set();
    this.marks = new Map();
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
}

function schedule(side, from, frame, inp, T, rand) {
  const jitter = 15 + Math.floor(rand() * 70); // 15–85 ms
  const at = Math.max(side.lane, T + jitter);
  side.lane = at;
  side.queue.push({ at, from, frame, inp });
}

function deliver(side, T) {
  let i = 0;
  while (i < side.queue.length) {
    if (side.queue[i].at <= T) {
      const item = side.queue.splice(i, 1)[0];
      side.sim.setInput(item.from, item.frame, item.inp);
    } else i += 1;
  }
}

function nextAt(side) {
  let n = Infinity;
  for (const item of side.queue) if (item.at < n) n = item.at;
  return n;
}

async function main() {
  const dmg = oneSwingDamage();
  check(dmg === 12, 'one heavy punch should deal 12, got ' + dmg + ' (multi-hit swing)');

  const srv = createServer();
  const port = await srv.listen(0, '127.0.0.1');
  const summary = { frames: 0, hashes: 0, mismatches: 0, result: null };
  try {
    const a = new Side(port, 'lock-a', 0, 0);
    const b = new Side(port, 'lock-b', 1, 0);
    await a.ready;
    await b.ready;
    a.send({ t: 'create' });
    const created = await a.wait((m) => m.t === 'created');
    b.send({ t: 'join', room: created.room });
    const joined = await b.wait((m) => m.t === 'joined' || m.t === 'error');
    check(joined.t === 'joined' && joined.slot === 1, 'join failed');
    a.send({ t: 'pick', char: 'kairo' });
    b.send({ t: 'pick', char: 'lyra' });
    a.send({ t: 'ready', ready: true, readySeq: 1 });
    b.send({ t: 'ready', ready: true, readySeq: 1 });
    const cdA = await a.wait((m) => m.t === 'countdown');
    const cdB = await b.wait((m) => m.t === 'countdown');
    check(cdA.delay === 3 && cdB.delay === 3, 'delay not agreed');
    check(cdA.seed === cdB.seed, 'seed mismatch');
    a.send({ t: 'loaded', startId: cdA.startId, epoch: cdA.epoch });
    b.send({ t: 'loaded', startId: cdB.startId, epoch: cdB.epoch });
    const goA = await a.wait((m) => m.t === 'go');
    const goB = await b.wait((m) => m.t === 'go');
    check(goA.seed === goB.seed && goA.delay === 3, 'go delay/seed');
    // Rebuild sims with the server seed so the test matches the protocol.
    a.sim = createMatch({ p0: 'kairo', p1: 'lyra', seed: goA.seed, delay: goA.delay, frames: meta.characters });
    b.sim = createMatch({ p0: 'kairo', p1: 'lyra', seed: goB.seed, delay: goB.delay, frames: meta.characters });
    a.msgs.length = 0;
    b.msgs.length = 0;

    const randA = mulberry(11);
    const randB = mulberry(29);
    const randNet = mulberry(77);
    let T = 0;
    let sends = 0;
    let windowStart = Date.now();

    function commit(side, rand, frame) {
      if (side.sent.has(frame)) return;
      const inp = randomInput(rand);
      if (!side.sim.setInput(side.slot, frame, inp)) return;
      side.sent.add(frame);
      side.pending.push({ frame, inp: cloneInput(inp) });
    }
    function flush(side) {
      if (!side.pending.length) return;
      const batch = side.pending.splice(0, 30);
      side.send({ t: 'input', batch });
      sends += 1;
    }
    for (let f = 0; f < 3; f++) {
      commit(a, randA, f);
      commit(b, randB, f);
    }
    flush(a);
    flush(b);

    let guard = 0;
    let netWaits = 0;
    while (Math.min(a.sim.frame, b.sim.frame) < FRAMES && !a.sim.result && !b.sim.result) {
      if (++guard > FRAMES * 20) throw new Error('lockstep did not advance, frames ' + a.sim.frame + '/' + b.sim.frame);
      await new Promise((r) => setImmediate(r));
      for (const side of [a, b]) {
        const incoming = side.msgs.splice(0);
        for (const m of incoming) {
          if (m.t !== 'input') continue;
          const from = m.from;
          const items = Array.isArray(m.batch) && m.batch.length
            ? m.batch
            : (typeof m.frame === 'number' ? [{ frame: m.frame, inp: m.inp }] : []);
          for (const item of items) {
            if (typeof item.frame !== 'number') continue;
            schedule(side, from, item.frame, item.inp, T, randNet);
          }
        }
        deliver(side, T);
      }
      let moved = false;
      for (const [side, rand] of [[a, randA], [b, randB]]) {
        let n = 0;
        while (side.sim.canStep() && n < 4 && !side.sim.result && side.sim.frame < FRAMES) {
          side.sim.step();
          n += 1;
          moved = true;
          if (side.sim.frame % HASH_EVERY === 0) side.marks.set(side.sim.frame, side.sim.hash());
          commit(side, rand, side.sim.frame - 1 + side.sim.delay);
        }
        flush(side);
      }
      for (const [frame, ha] of a.marks) {
        if (!b.marks.has(frame) || a.checked?.has(frame)) continue;
        const hb = b.marks.get(frame);
        summary.hashes += 1;
        a.checked = a.checked || new Set();
        a.checked.add(frame);
        if (ha !== hb) {
          summary.mismatches += 1;
          throw new Error(`hash mismatch at frame ${frame}: ${ha} vs ${hb}`);
        }
      }
      if (!moved) {
        const next = Math.min(nextAt(a), nextAt(b));
        if (!Number.isFinite(next)) {
          // The relay delivery is real; give the socket a moment before calling it a stall.
          if (netWaits++ < 50) {
            await sleep(5);
            continue;
          }
          throw new Error(`stalled at ${a.sim.frame}/${b.sim.frame} msgs ${a.msgs.length}/${b.msgs.length} q ${a.queue.length}/${b.queue.length} sent ${a.sent.size}/${b.sent.size}`);
        }
        netWaits = 0;
        T = next;
      }
      if (sends >= 80) {
        const elapsed = Date.now() - windowStart;
        if (elapsed < 1000) await sleep(1000 - elapsed);
        sends = 0;
        windowStart = Date.now();
      }
    }
    check(a.sim.frame === b.sim.frame, `frame split ${a.sim.frame} vs ${b.sim.frame}`);
    check(a.sim.hash() === b.sim.hash(), 'final hash mismatch');
    check(a.sim.result === b.sim.result, 'result mismatch ' + a.sim.result + ' ' + b.sim.result);
    check(a.sim.frame >= FRAMES, `match ended at frame ${a.sim.frame} via ${a.sim.result}, wanted ${FRAMES}`);
    const expectMarks = Math.floor(FRAMES / HASH_EVERY);
    check(summary.hashes === expectMarks, `checked ${summary.hashes} hashes, wanted ${expectMarks}`);
    summary.frames = a.sim.frame;
    summary.result = a.sim.result;
    summary.hp = [a.sim.fighters[0].hp, a.sim.fighters[1].hp];
    console.log(JSON.stringify({ ok: true, oneSwing: dmg, summary }, null, 2));
    a.ws.close();
    b.ws.close();
  } finally {
    await srv.close();
  }
}

main().catch((err) => {
  console.error('FAIL', err && err.stack || err);
  process.exit(1);
});
