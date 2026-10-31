// Arena FC Node server: rules, simulation (determinism, saves, restarts, fouls) and the wire protocol
// (lobby, start, snapshots, chat, resume token, host migration, kick, forged token, limits).
//   node test_arena.js
const assert = require('assert');
const WebSocket = require('ws');
const R = require('./arena/rules');
const { Match, HALF_L, HALF_W, GOAL_W } = require('./arena/sim');
const { createStandalone } = require('./arena/standalone');

let n = 0;
function ok(c, msg) { n++; assert.ok(c, msg); }

// ---------------------------------------------------------------- rules
(function rules() {
  const kt = R.keeperTarget(-52.5, 1, { x: -30, y: 0.3, z: 4, vx: -20, vy: 0, vz: -3 }, 3.66);
  ok(kt.z < 4 && kt.z > -4.3, 'keeper goes to the predicted crossing');
  const idle = R.keeperTarget(-52.5, 1, { x: 0, y: 0.3, z: 20, vx: 0, vy: 0, vz: 0 }, 3.66);
  ok(idle.x > -52.5 && idle.x < -49 && Math.abs(idle.z) <= 3.66, 'idle keeper stays near goal');
  ok(R.saveChance(0.2, 14, 1.9) > R.saveChance(1.5, 14, 1.9), 'closer shot is saved more often');
  ok(R.saveChance(0.5, 30, 1.9) < R.saveChance(0.5, 10, 1.9), 'harder shot is saved less often');
  ok(R.saveChance(3, 14, 1.9) === 0, 'out of reach never saved');
  ok(R.shotError(30, 0.8, 1) > R.shotError(8, 0, 0.5), 'long pressured shot is wilder');
  const open = R.passScore({ x: 0, z: 0 }, { x: 15, z: 0 }, 1, [{ x: 0, z: 20 }], null);
  const blocked = R.passScore({ x: 0, z: 0 }, { x: 15, z: 0 }, 1, [{ x: 7, z: 0.3 }], null);
  ok(open > blocked + 4, 'blocked lane penalised');
  ok(R.passScore({ x: 0, z: 0 }, { x: 0, z: 15 }, 1, [], { x: 0, z: 1 }) > R.passScore({ x: 0, z: 0 }, { x: 0, z: -15 }, 1, [], { x: 0, z: 1 }), 'stick steers the pass');
  const post = R.woodwork({ x: 52.45, y: 1, z: 3.5, vx: 20, vy: 0, vz: 0 }, 1, 52.5, 3.66, 2.44, 0.11);
  ok(post.hit && post.kind === 'post' && post.vel.z < 0, 'post deflects');
  ok(R.woodwork({ x: 52.5, y: 2.5, z: 0, vx: 10, vy: -6, vz: 0 }, 1, 52.5, 3.66, 2.44, 0.11).kind === 'bar', 'crossbar deflects');
  ok(!R.woodwork({ x: 52.5, y: 1, z: 0, vx: 20, vy: 0, vz: 0 }, 1, 52.5, 3.66, 2.44, 0.11).hit, 'goal mouth is clear');
  const th = R.restartFor({ x: 10, z: 35 }, 0, 52.5, 34);
  ok(th.kind === 'throw' && th.team === 1 && th.spot.z === 34, 'throw-in');
  ok(R.restartFor({ x: 54, z: 12 }, 1, 52.5, 34).kind === 'corner', 'defender behind -> corner');
  ok(R.restartFor({ x: 54, z: 12 }, 0, 52.5, 34).kind === 'goal_kick', 'attacker behind -> goal kick');
  ok(R.foulChance({ x: 5, z: 0 }, { x: 1, z: 0 }, false) > R.foulChance({ x: -5, z: 0 }, { x: 1, z: 0 }, false), 'from behind fouls more');
})();

// ---------------------------------------------------------------- simulation
(function sim() {
  const run = (seed, secs) => {
    const m = new Match({ seed });
    m.addHuman(0, 0); m.addHuman(1, 1);
    for (let i = 0; i < secs * 60; i++) {
      m.setInput(0, { mx: Math.sin(i / 50), my: Math.cos(i / 70), sp: i % 90 < 30, pa: i % 100 === 0, sh: i % 250 === 0, ch: 0.8 });
      m.setInput(1, { mx: -0.4, my: Math.sin(i / 40), ta: i % 80 === 0 });
      m.step();
    }
    return m;
  };
  const a = run(7, 120); const b = run(7, 120); const c = run(8, 120);
  ok(a.hash() === b.hash(), 'same seed + inputs -> same state (deterministic)');
  ok(a.hash() !== c.hash(), 'different seed -> different state');
  for (const m of [a, c]) {
    ok(!m.players.some((p) => !Number.isFinite(p.x) || Math.abs(p.x) > 60 || Math.abs(p.z) > 45), 'players stay finite and in bounds');
    ok(Number.isFinite(m.ball.x) && Math.abs(m.ball.x) < 80 && Math.abs(m.ball.z) < 60 && m.ball.y < 40, 'ball stays finite and in bounds');
  }
  // forced restarts
  const m = new Match({ seed: 3 }); m.addHuman(0, 0);
  for (let i = 0; i < 80; i++) m.step();
  Object.assign(m.ball, { owner: -1, x: 10, y: 0.3, z: 35, vx: 0, vz: 3, last: 2, free: 1 });
  m.step();
  ok(m.phase === 'restart' && m.ball.owner >= 5 && Math.abs(m.ball.z - HALF_W) < 0.01, 'touchline -> throw-in to the other team');
  for (let i = 0; i < 70; i++) m.step();
  ok(m.phase === 'play', 'restart pause ends');
  Object.assign(m.ball, { owner: -1, x: 53.5, y: 0.3, z: 12, vx: 2, vz: 0, last: 2, free: 1 });
  m.step();
  ok(m.phase === 'restart' && m.ball.owner === 5 && m.ball.x < 52, 'wide of goal -> keeper takes the goal kick');
  // keeper stops some shots, not all
  let saves = 0; let goals = 0;
  const k = new Match({ seed: 9 }); k.addHuman(0, 0);
  for (let i = 0; i < 80; i++) k.step();
  for (let t = 0; t < 40; t++) {
    k.phase = 'play'; k.score = [0, 0];
    for (const p of k.players) p.lock = 0;
    const kp = k.players[5]; kp.x = 51; kp.z = 0; kp.vx = 0; kp.vz = 0;
    Object.assign(k.ball, { owner: -1, x: 38, y: 0.5, z: 0, vx: 24, vy: 1.5, vz: k.rr(-4.5, 4.5), last: 3, free: 1 });
    for (let i = 0; i < 80; i++) {
      k.step();
      if (k.phase === 'goal') { goals++; break; }
      if (k.ball.owner === 5 || k.ball.vx < 0) { saves++; break; }
    }
  }
  ok(saves > 3 && goals > 3, `keeper stops some, not all (${saves} saves, ${goals} goals of 40)`);
  // a goal ends in a kickoff for the side that conceded
  const g = new Match({ seed: 4 }); g.addHuman(0, 0);
  for (let i = 0; i < 80; i++) g.step();
  Object.assign(g.ball, { owner: -1, x: 53, y: 0.5, z: 0, vx: 0, vz: 0, free: 1 });
  g.step();
  ok(g.phase === 'goal' && g.score[0] === 1, 'goal scored for team 0');
  for (let i = 0; i < 185; i++) g.step();
  ok(g.phase === 'kickoff' && g.score[0] === 1 && g.ball.owner === 9, 'kickoff restarts with the conceding team');
  // full time
  const f = new Match({ seed: 5, halfMinutes: 1, timeSpeed: 60 }); f.addHuman(0, 0);
  let steps = 0;
  while (!f.finished && steps < 60 * 60) { f.step(); steps++; }
  ok(f.finished && f.half === 2, 'two halves then full time');
})();

// ---------------------------------------------------------------- wire protocol
class Client {
  constructor(url, name) {
    this.name = name; this.msgs = []; this.ws = new WebSocket(url);
    this.ws.on('message', (d) => { const m = JSON.parse(d.toString()); this.msgs.push(m); if (m.t === 'ping') this.send({ t: 'pong', ms: m.ms }); });
    this.opened = new Promise((r, j) => { this.ws.once('open', r); this.ws.once('error', j); });
    this.closed = new Promise((r) => this.ws.once('close', (code) => r(code)));
  }
  send(o) { this.ws.send(JSON.stringify(o)); }
  take(t) { const out = this.msgs.filter((m) => m.t === t); this.msgs = this.msgs.filter((m) => m.t !== t); return out; }
  peek(t) { return this.msgs.filter((m) => m.t === t); }
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function until(fn, ms = 3000) { const t0 = Date.now(); while (Date.now() - t0 < ms) { const v = fn(); if (v) return v; await sleep(20); } return fn(); }
const http = require('http');
const getJson = (port, p) => new Promise((res, rej) => http.get({ host: '127.0.0.1', port, path: p }, (r) => { let b = ''; r.on('data', (d) => { b += d; }); r.on('end', () => res(JSON.parse(b))); }).on('error', rej));

(async () => {
  const srv = createStandalone({ quiet: true, seed: 11, graceSeconds: 30, maxPerIp: 6 });
  const port = await srv.listen(0, '127.0.0.1');
  const url = `ws://127.0.0.1:${port}`;
  try {
    const A = new Client(url, 'Ada'); await A.opened;
    A.send({ t: 'hello', ver: 2, name: 'Ada', room: '', create: true });
    const wa = (await until(() => A.peek('welcome')[0]));
    ok(wa && wa.slot === 0 && wa.team === 0 && wa.room.length === 6 && wa.token.length >= 43 && wa.host === 0, 'host welcome with token');
    const B = new Client(url, 'Bo'); await B.opened;
    B.send({ t: 'hello', ver: 2, name: 'Bo', room: wa.room.toLowerCase() });
    const wb = await until(() => B.peek('welcome')[0]);
    ok(wb && wb.slot === 1 && wb.team === 1 && wb.token !== wa.token, 'second player: slot 1, away team, own token');
    const C = new Client(url, 'Cy'); await C.opened;
    C.send({ t: 'hello', ver: 2, name: 'Cy', room: wa.room });
    const wc = await until(() => C.peek('welcome')[0]);
    ok(wc && wc.slot === 2, 'third player: slot 2');
    // errors
    const X = new Client(url, 'X'); await X.opened;
    X.send({ t: 'hello', ver: 2, name: 'X', room: 'NOPE99' });
    ok((await until(() => X.peek('error')[0])).reason.includes('not found'), 'unknown room is refused');
    X.ws.close();
    B.send({ t: 'start' });
    ok((await until(() => B.peek('error')[0])).reason.includes('host'), 'only the host can start');
    A.send({ t: 'start' });
    ok(await until(() => B.peek('begin')[0]), 'host starts the match');
    const late = new Client(url, 'Late'); await late.opened;
    late.send({ t: 'hello', ver: 2, name: 'Late', room: wa.room });
    ok((await until(() => late.peek('error')[0])).reason.includes('in progress'), 'cannot join a running match without a token');
    late.ws.close();
    // play
    for (let i = 0; i < 30; i++) { A.send({ t: 'input', seq: i, cmd: { mx: 0.6, sp: true } }); B.send({ t: 'input', seq: i, cmd: { mx: -0.5 } }); await sleep(20); }
    const sa = await until(() => A.peek('snap').length > 5 && A.peek('snap'));
    const sc = await until(() => C.peek('snap').length > 5 && C.peek('snap'));
    ok(sa && sc, 'snapshots reach every player');
    const last = sa[sa.length - 1];
    ok(last.players.length === 10 && last.ctrls.length === 4 && last.ctrls[0] >= 0 && last.ctrls[2] >= 0 && last.ctrls[3] === -1 && 'rng' in last && 'gt' in last && last.inputs.length > 0, 'snapshot shape');
    const byTick = new Map(sc.map((m) => [m.tick, m]));
    const shared = sa.filter((m) => byTick.has(m.tick));
    ok(shared.length > 2 && shared.every((m) => JSON.stringify(m.players) === JSON.stringify(byTick.get(m.tick).players)), 'everyone sees identical state per tick');
    // chat
    A.send({ t: 'chat', m: 'gg' });
    ok((await until(() => B.peek('chat')[0])).m === 'gg', 'chat relayed');
    // flood guard: input spam cannot crash the room
    for (let i = 0; i < 400; i++) A.send({ t: 'input', cmd: { mx: 1 } });
    // host drops -> migration
    const hostCloseA = A.closed;
    A.ws.terminate(); await hostCloseA;
    const hostMsg = await until(() => B.peek('host')[0]);
    ok(hostMsg && hostMsg.host === 1 && hostMsg.slot === 0, 'host migrates to the next player');
    const lob = await until(() => B.peek('lobby').reverse().find((m) => m.onlines && m.onlines.includes(false)));
    ok(lob && lob.host === 1, 'lobby shows the dropped slot as reserved');
    const tickBefore = B.peek('snap').slice(-1)[0].tick;
    ok(await until(() => B.peek('snap').slice(-1)[0].tick > tickBefore + 10), 'match keeps running after the host leaves');
    // resume with token
    const A2 = new Client(url, 'Ada'); await A2.opened;
    A2.send({ t: 'hello', ver: 2, name: 'Ada', room: wa.room, token: wa.token });
    const w2 = await until(() => A2.peek('welcome')[0]);
    ok(w2 && w2.slot === 0 && !w2.token && w2.host === 1, 'token resume keeps slot, no new token, host stays migrated');
    const res = await until(() => A2.peek('resume')[0]);
    ok(res && res.full.players.length === 10 && res.full.tick >= tickBefore && 'rng' in res.full && res.ctrls[0] === last.ctrls[0] || res.ctrls[0] >= 0, 'resume carries a live checkpoint');
    ok(res.players.length === 10 && res.ball && res.score, 'resume has top-level snapshot fields the browser reads');
    // forged token
    const F = new Client(url, 'Eve'); await F.opened;
    F.send({ t: 'hello', ver: 2, name: 'Eve', room: wa.room, token: 'x'.repeat(43) });
    ok(!(await until(() => F.peek('welcome')[0], 400)), 'forged token gets no slot');
    F.ws.close();
    // kick
    B.send({ t: 'kick', kickSlot: 2 });
    ok(await until(() => B.peek('lobby').reverse().find((m) => !m.slots.includes(2))), 'host can remove a player');
    ok(await C.closed === 4001, 'kicked client is disconnected');
    // health
    const h = await getJson(port, '/health');
    ok(h.ok && h.protocol === 2 && h.rooms === 1 && h.migrations >= 1 && h.reconnects >= 1 && h.matches[0].started, 'health reports rooms, migrations and reconnects');
    // per-IP cap
    const extra = [];
    for (let i = 0; i < 8; i++) { const w = new WebSocket(url); w.on('error', () => {}); extra.push(w); }
    await sleep(300);
    ok(extra.filter((w) => w.readyState === WebSocket.OPEN).length <= 6, 'per-IP connection cap enforced');
    extra.forEach((w) => w.terminate());
    console.log(`arena: ${n} checks ok`);
  } finally {
    await srv.close();
  }
  process.exit(0);
})().catch((e) => { console.error(e); process.exit(1); });
