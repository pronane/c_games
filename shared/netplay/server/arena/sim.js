// Server-side Arena FC 5-a-side match. A port of the browser edition's offline simulation
// (arena-fc/Web/BrowserBoot.gd step_offline + MatchRules.gd) so online matches play like the offline game.
// Deterministic: same seed + same inputs on the same ticks -> same state. 60 Hz fixed step.
'use strict';
const R = require('./rules');

const HALF_L = 52.5; const HALF_W = 34.0; const GOAL_W = 3.66; const GOAL_H = 2.44; const BALL_R = 0.11;
const TEAM = 5;
const DT = 1 / 60;
const FORMATION = [[-0.86, 0], [-0.52, 0], [-0.12, -0.48], [-0.12, 0.48], [0.10, 0]];

function mulberry32(seed) {
  let a = seed >>> 0;
  const f = () => {
    a = (a + 0x6D2B79F5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  f.getState = () => a;
  f.setState = (s) => { a = s >>> 0; };
  return f;
}

class Match {
  // opts: seed, halfMinutes (game minutes per half), timeSpeed (game seconds per real second)
  constructor(opts = {}) {
    this.rand = mulberry32(opts.seed === undefined ? 2026 : opts.seed);
    this.halfSeconds = (opts.halfMinutes || 45) * 60;
    this.timeSpeed = opts.timeSpeed || 15;
    this.tick = 0;
    this.clock = 0;
    this.half = 1;
    this.score = [0, 0];
    this.feed = [];
    this.humans = [];          // {slot, team, ctrl, mx, my, sp, charge, pending}
    this.finished = false;
    this.phase = 'kickoff';
    this.phaseTimer = 1.0;
    this.switchCd = 0;
    this.inputLog = [];        // trailing [{t, c:{slot: cmd}}]
    this.resetPositions(0);
  }

  randn(sd) {                  // Box-Muller
    const u = Math.max(1e-9, this.rand()); const v = this.rand();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v) * sd;
  }
  rr(a, b) { return a + (b - a) * this.rand(); }

  say(text) {
    this.feed.push(text);
    if (this.feed.length > 3) this.feed.shift();
  }

  // ------------------------------------------------------------------ setup
  resetPositions(kickTeam) {
    this.players = [];
    for (let side = 0; side < 2; side++) {
      const sign = side === 0 ? 1 : -1;
      for (let i = 0; i < TEAM; i++) {
        const x = sign * FORMATION[i][0] * HALF_L * 0.94;
        const z = FORMATION[i][1] * HALF_W * 0.88;
        this.players.push({
          team: side, slot: i, x, z, hx: x, hz: z, vx: 0, vz: 0, fx: sign, fz: 0,
          phase: this.rand() * 6.28, keeper: i === 0, action: 'idle', atime: 0, lock: 0, hold: 0, reading: false, kerr: 0,
        });
      }
    }
    const starter = kickTeam * TEAM + (TEAM - 1);
    this.ball = { x: 0, y: BALL_R, z: 0, vx: 0, vy: 0, vz: 0, owner: starter, free: 0, last: starter };
    const sp = this.players[starter];
    sp.x = -(kickTeam === 0 ? 1 : -1) * 0.5; sp.z = 0;
    // humans keep a controlled outfield player on their team
    for (const h of this.humans) {
      if (h.ctrl < 0 || this.players[h.ctrl].team !== h.team) h.ctrl = this.defaultCtrl(h);
    }
  }

  defaultCtrl(h) {
    // slot 0/1 take the last outfield player of their team, slots 2/3 the one before it
    const idx = Math.floor(h.slot / 2);
    return h.team * TEAM + (TEAM - 1 - idx);
  }

  addHuman(slot, team) {
    const h = { slot, team, ctrl: -1, mx: 0, my: 0, sp: false, charge: 0, chargeAcc: 0, pending: {}, last: { x: team === 0 ? 1 : -1, z: 0 } };
    h.ctrl = this.defaultCtrl(h);
    this.humans.push(h);
    return h;
  }

  removeHuman(slot) {
    this.humans = this.humans.filter((h) => h.slot !== slot);
  }

  humanOf(i) { return this.humans.findIndex((h) => h.ctrl === i); }

  // Latest command from a client. Held values overwrite; one-shot buttons latch until consumed.
  setInput(slot, cmd) {
    const h = this.humans.find((q) => q.slot === slot);
    if (!h || !cmd || typeof cmd !== 'object') return;
    h.mx = R.clamp(Number(cmd.mx) || 0, -1, 1);
    h.my = R.clamp(Number(cmd.my) || 0, -1, 1);
    h.sp = !!cmd.sp;
    for (const k of ['pa', 'th', 'ta', 'sw', 'lo']) if (cmd[k]) h.pending[k] = true;
    if (cmd.sh) { h.pending.sh = true; h.pending.ch = R.clamp(Number(cmd.ch) || 0.5, 0.25, 1); }
  }

  // ------------------------------------------------------------------ helpers
  teamOwner() { return this.ball.owner < 0 ? -1 : this.players[this.ball.owner].team; }
  opps(team) { return this.players.filter((q) => q.team !== team); }
  dBall(p) { return Math.hypot(p.x - this.ball.x, p.z - this.ball.z); }

  chaseRank(i) {
    const mine = this.dBall(this.players[i]);
    let rank = 0;
    for (let j = 0; j < this.players.length; j++) {
      const q = this.players[j];
      if (j !== i && q.team === this.players[i].team && !q.keeper && this.dBall(q) < mine - 0.001) rank++;
    }
    return rank;
  }

  nearestOutfield(team, x, z) {
    let best = -1; let bd = 1e9;
    for (let j = 0; j < this.players.length; j++) {
      const q = this.players[j];
      if (q.team === team && !q.keeper) { const d = Math.hypot(q.x - x, q.z - z); if (d < bd) { bd = d; best = j; } }
    }
    return best;
  }

  setAction(p, a, dur) { p.action = a; p.atime = dur; }

  assignCtrl(team, i) {
    // hand the controlled player to the (single) human of that team nearest the new carrier
    const hs = this.humans.filter((h) => h.team === team);
    if (hs.length === 0 || this.players[i].keeper) return;
    let pick = hs[0];
    let bd = 1e9;
    for (const h of hs) {
      const d = Math.hypot(this.players[h.ctrl].x - this.players[i].x, this.players[h.ctrl].z - this.players[i].z);
      if (d < bd) { bd = d; pick = h; }
    }
    if (!hs.some((h) => h.ctrl === i)) pick.ctrl = i;
  }

  // ------------------------------------------------------------------ actions
  passBall(from, through, lob, inputDir) {
    if (this.ball.owner !== from) return;
    const p = this.players[from];
    const sign = p.team === 0 ? 1 : -1;
    const hk = this.humanOf(from);
    const opps = this.opps(p.team);
    let best = -1; let bs = -1e9;
    for (let j = 0; j < this.players.length; j++) {
      const q = this.players[j];
      if (q.team !== p.team || j === from) continue;
      let sc = R.passScore(p, q, sign, opps, hk >= 0 ? inputDir : null);
      if (q.keeper) sc -= 8;
      sc += this.rand() * 0.8;
      if (sc > bs) { bs = sc; best = j; }
    }
    if (best < 0) return;
    const b = this.ball;
    b.owner = -1;
    p.lock = 0.4;
    this.setAction(p, 'kick', 0.3);
    const r = this.players[best];
    const d = Math.hypot(p.x - r.x, p.z - r.z);
    const spd = R.passSpeed(d, through) * (lob ? 0.85 : 1);
    const lead = R.leadPoint(b, r, r, spd, through ? 0.9 : 0.15);
    if (through) lead.x += sign * 3;
    let dx = lead.x - b.x; let dz = lead.z - b.z;
    const l = Math.hypot(dx, dz) || 1;
    dx /= l; dz /= l;
    const a = this.rr(-0.04, 0.04);
    const ca = Math.cos(a); const sa = Math.sin(a);
    const rx = dx * ca - dz * sa; const rz = dx * sa + dz * ca;
    b.vx = rx * spd; b.vz = rz * spd;
    b.vy = 0.4 + (through ? 1.2 : 0) + d * 0.03 + (lob ? 4.5 + d * 0.12 : 0);
    b.x += rx * 0.5; b.z += rz * 0.5; b.y += 0.03;
    b.free = 0; b.last = from;
    if (hk >= 0 && !r.keeper) this.humans[hk].ctrl = best;
    this.say(lob ? 'Chip!' : through ? 'Through ball.' : 'Pass.');
  }

  shoot(from, power, aimZ) {
    if (this.ball.owner !== from) return;
    const p = this.players[from];
    const sign = p.team === 0 ? 1 : -1;
    const b = this.ball;
    b.owner = -1;
    p.lock = 0.6;
    this.setAction(p, 'kick', 0.4);
    let keeperZ = 0;
    for (const q of this.players) if (q.keeper && q.team !== p.team) keeperZ = q.z;
    let pick = (Math.abs(keeperZ) > 0.3 ? -Math.sign(keeperZ) : (this.rand() < 0.5 ? 1 : -1)) * GOAL_W * 0.72;
    pick = R.clamp(pick + (aimZ || 0) * GOAL_W * 0.4, -GOAL_W * 0.92, GOAL_W * 0.92);
    const tx = sign * HALF_L; const ty = this.rr(0.35, 1.7); const tz = pick;
    let dx = tx - b.x; let dy = ty - b.y; let dz = tz - b.z;
    const dist = Math.hypot(dx, dy, dz);
    const err = R.shotError(dist, R.pressure(p, this.opps(p.team)), power);
    let l = Math.hypot(dx, dz) || 1;
    dx /= l; dz /= l;
    const a = this.randn(err);
    const ca = Math.cos(a); const sa = Math.sin(a);
    const rx = dx * ca - dz * sa; const rz = dx * sa + dz * ca;
    const vy = dy / (dist || 1) + this.randn(err * 0.5);
    l = Math.hypot(rx, vy, rz);
    const spd = 18 + (29 - 18) * power;
    b.vx = (rx / l) * spd; b.vy = (vy / l) * spd + (1.2 + (4.5 - 1.2) * power); b.vz = (rz / l) * spd;
    b.free = 0; b.last = from;
    this.say('Shot!');
  }

  tryTackle(tackler, victim, sliding) {
    const t = this.players[tackler]; const v = this.players[victim];
    t.lock = 0.5;
    this.setAction(t, sliding ? 'slide' : 'tackle', 0.45);
    if (this.rand() < R.foulChance({ x: t.vx, z: t.vz }, { x: v.fx, z: v.fz }, sliding)) {
      this.say('Foul!  Free kick.');
      this.restartWith(v.team, { x: R.clamp(v.x, -HALF_L + 1, HALF_L - 1), z: R.clamp(v.z, -HALF_W + 1, HALF_W - 1) }, 'Free kick');
      return;
    }
    this.ball.owner = tackler;
    this.say('Tackle!');
  }

  restartWith(team, spot, label) {
    let taker = this.nearestOutfield(team, spot.x, spot.z);
    if (label === 'Goal kick') taker = team * TEAM;
    for (const p of this.players) { p.vx = 0; p.vz = 0; }
    const tk = this.players[taker];
    tk.x = spot.x; tk.z = spot.z; tk.lock = 0;
    const b = this.ball;
    b.x = spot.x; b.y = BALL_R; b.z = spot.z; b.vx = 0; b.vy = 0; b.vz = 0;
    b.owner = taker; b.free = 0; b.last = taker;
    if (!tk.keeper) this.assignCtrl(team, taker);
    if (label !== 'Free kick') this.say(`${label}.`);
    this.phase = 'restart';
    this.phaseTimer = 0.9;
  }

  ballOut() {
    const last = this.ball.last >= 0 ? this.players[this.ball.last].team : 0;
    const r = R.restartFor(this.ball, last, HALF_L, HALF_W);
    this.restartWith(r.team, r.spot, { throw: 'Throw-in', corner: 'Corner', goal_kick: 'Goal kick' }[r.kind]);
  }

  goal(side) {
    this.score[side]++;
    this.say(`GOAL!  ${this.score[0]} - ${this.score[1]}`);
    for (const q of this.players) if (q.team === side && !q.keeper) { q.action = 'celebrate'; q.atime = 4; }
    this.phase = 'goal';
    this.phaseTimer = 3.0;
    this.conceded = 1 - side;
  }

  // ------------------------------------------------------------------ main step
  step(dt = DT) {
    this.tick++;
    const logC = {};
    for (const h of this.humans) {
      const c = {};
      if (h.mx) c.mx = h.mx;
      if (h.my) c.my = h.my;
      if (h.sp) c.sp = true;
      for (const k of Object.keys(h.pending)) c[k] = h.pending[k];
      if (Object.keys(c).length) logC[h.slot] = c;
    }
    this.inputLog.push({ t: this.tick, c: logC });
    if (this.inputLog.length > 12) this.inputLog.shift();

    for (const p of this.players) {
      p.atime -= dt;
      if (p.atime <= 0 && p.action !== 'celebrate') p.action = 'idle';
    }
    if (this.phase !== 'play') {
      this.phaseTimer -= dt;
      if (this.phaseTimer <= 0) {
        if (this.phase === 'goal') {
          this.resetPositions(this.conceded);
          this.phase = 'kickoff'; this.phaseTimer = 1.0;
        } else if (this.phase === 'kickoff' || this.phase === 'restart') {
          this.phase = 'play';
          if (this.phase === 'play') this.say('Back under way!');
        }
      }
      for (const h of this.humans) h.pending = {};
      return;
    }
    this.clock += dt * this.timeSpeed;
    if (this.clock >= this.half * this.halfSeconds) {
      if (this.half === 1) {
        this.half = 2; this.say('Half time.');
        this.resetPositions(1); this.phase = 'kickoff'; this.phaseTimer = 2.0;
      } else {
        this.finished = true;
        this.say('Full time.');
      }
      return;
    }
    this.stepPlay(dt);
  }

  stepPlay(dt) {
    const b = this.ball;
    // --- human one-shots ---
    for (const h of this.humans) {
      const me = h.ctrl;
      const mv = Math.hypot(h.mx, h.my);
      if (mv > 0.2) h.last = { x: h.mx, z: h.my };
      if (h.pending.sh && b.owner === me) this.shoot(me, h.pending.ch || 0.5, h.my);
      if (h.pending.pa) this.passBall(me, false, false, h.last);
      if (h.pending.th) this.passBall(me, true, false, h.last);
      if (h.pending.lo) this.passBall(me, false, true, h.last);
      if (h.pending.ta) {
        const o = b.owner;
        if (o >= 0 && this.players[o].team !== h.team && Math.hypot(this.players[me].x - this.players[o].x, this.players[me].z - this.players[o].z) < 2.2) {
          this.tryTackle(me, o, Math.hypot(this.players[me].vx, this.players[me].vz) > 4.5);
        }
      }
      if (h.pending.sw) {
        const best = this.nearestOutfield(h.team, b.x, b.z);
        if (best >= 0) h.ctrl = best;
      }
      h.pending = {};
    }
    // --- ball ---
    if (b.owner >= 0) {
      const o = this.players[b.owner];
      let fx = o.fx; let fz = o.fz;
      const fl = Math.hypot(fx, fz);
      if (fl < 0.1) { fx = 1; fz = 0; } else { fx /= fl; fz /= fl; }
      const run = R.clamp(Math.hypot(o.vx, o.vz) / 5, 0, 1);
      const touch = 0.5 + 0.18 * Math.sin(o.phase * 3) * run;
      b.x = o.x + fx * touch; b.z = o.z + fz * touch; b.y = BALL_R;
      b.vx = o.vx; b.vy = 0; b.vz = o.vz;
      b.last = b.owner;
    } else {
      b.vy -= 9.81 * dt;
      const drag = Math.max(0, 1 - 0.06 * dt);
      b.vx *= drag; b.vy *= drag; b.vz *= drag;
      b.x += b.vx * dt; b.y += b.vy * dt; b.z += b.vz * dt;
      if (b.y < BALL_R) {
        b.y = BALL_R;
        if (b.vy < 0) {
          b.vy = -b.vy * 0.48;
        }
        if (Math.abs(b.vy) < 0.45) b.vy = 0;
        const f = Math.max(0, 1 - 1.5 * dt);
        b.vx *= f; b.vz *= f;
      }
      b.free += dt;
      for (const side of [-1, 1]) {
        const w = R.woodwork(b, side, HALF_L, GOAL_W, GOAL_H, BALL_R);
        if (w.hit) {
          b.x = w.pos.x; b.y = w.pos.y; b.z = w.pos.z; b.vx = w.vel.x; b.vy = w.vel.y; b.vz = w.vel.z;
          this.say(w.kind === 'post' ? 'Off the woodwork!' : 'Off the bar!');
          break;
        }
      }
    }
    // --- players ---
    const teamHas = this.teamOwner();
    for (let i = 0; i < this.players.length; i++) {
      const p = this.players[i];
      p.lock = Math.max(0, p.lock - dt);
      const sign = p.team === 0 ? 1 : -1;
      const goalX = sign * HALF_L;
      const ownX = -sign * HALF_L;
      let wx = 0; let wz = 0; let speed = 5.4;
      const hi = this.humanOf(i);
      if (p.keeper) {
        const heading = b.owner < 0 && -sign * b.vx > 8;
        const kt = R.keeperTarget(ownX, sign, b, GOAL_W);
        if (heading) {
          if (!p.reading) { p.reading = true; p.kerr = this.randn(0.9 + Math.hypot(b.vx, b.vy, b.vz) * 0.05); }
          kt.z = R.clamp(kt.z + p.kerr, -GOAL_W - 0.6, GOAL_W + 0.6);
        } else p.reading = false;
        const tx = kt.x - p.x; const tz = kt.z - p.z; const tl = Math.hypot(tx, tz);
        if (tl > 0.2) { wx = tx / tl; wz = tz / tl; }
        speed = heading ? 8.0 : 6.0;
        if (heading && tl > 0.6) this.setAction(p, 'dive', 0.3);
        if (b.owner === i) {
          p.hold += dt; wx = 0; wz = 0;
          if (p.hold > 1.1) { p.hold = 0; this.passBall(i, false, false, null); }
        } else p.hold = 0;
      } else if (hi >= 0) {
        const h = this.humans[hi];
        wx = h.mx; wz = h.my;
        const l = Math.hypot(wx, wz); if (l > 1) { wx /= l; wz /= l; }
        if (h.sp && l > 0.1) speed *= 1.3;
      } else if (b.owner === i) {
        [wx, wz] = this.aiCarrier(i, p, goalX, dt);
        speed = 5.6;
      } else {
        [wx, wz] = this.aiOffBall(i, p, sign, teamHas, dt);
        if (teamHas !== p.team && this.chaseRank(i) < 2) speed = 5.9;
      }
      const k = Math.min(1, dt * 8);
      p.vx += (wx * speed - p.vx) * k; p.vz += (wz * speed - p.vz) * k;
      p.x += p.vx * dt; p.z += p.vz * dt;
      p.x = R.clamp(p.x, -HALF_L - 2, HALF_L + 2); p.z = R.clamp(p.z, -HALF_W - 2, HALF_W + 2);
      const vl = Math.hypot(p.vx, p.vz);
      if (vl > 0.2) {
        const t = Math.min(1, dt * 12);
        let nx = p.fx + (p.vx / vl - p.fx) * t; let nz = p.fz + (p.vz / vl - p.fz) * t;
        const nl = Math.hypot(nx, nz) || 1;
        p.fx = nx / nl; p.fz = nz / nl;
      }
      p.phase += dt * (2 + vl);
    }
    this.keeperSaves();
    // --- loose ball pickup ---
    if (b.owner < 0 && b.free > 0.1 && b.y < 1.4) {
      for (let i = 0; i < this.players.length; i++) {
        const q = this.players[i];
        if (q.lock > 0) continue;
        if (Math.hypot(q.x - b.x, q.z - b.z) < 1.05) {
          b.owner = i; b.vx = b.vy = b.vz = 0; b.free = 0; b.last = i;
          if (!q.keeper) this.assignCtrl(q.team, i);
          break;
        }
      }
    }
    this.autoSwitch(dt);
    // --- rules ---
    if (Math.abs(b.x) > HALF_L && Math.abs(b.z) < GOAL_W && b.y < GOAL_H) { this.goal(b.x > 0 ? 0 : 1); return; }
    if (Math.abs(b.x) > HALF_L + 0.6 || Math.abs(b.z) > HALF_W + 0.6) this.ballOut();
  }

  aiCarrier(i, p, goalX, dt) {
    let tx = goalX - p.x; let tz = -p.z;
    const dg = Math.hypot(tx, tz) || 1;
    const dirx = tx / dg; const dirz = tz / dg;
    let ax = 0; let az = 0;
    for (const q of this.players) {
      if (q.team === p.team) continue;
      const dx = q.x - p.x; const dz = q.z - p.z; const l = Math.hypot(dx, dz);
      if (l < 4.5 && l > 0.01 && (dx / l) * dirx + (dz / l) * dirz > 0.2) {
        let sx = -dz / l; let sz = dx / l;
        if (sx * dirx + sz * dirz < 0) { sx = -sx; sz = -sz; }
        ax += sx * (4.5 - l) / 4.5; az += sz * (4.5 - l) / 4.5;
      }
    }
    const pr = R.pressure(p, this.opps(p.team));
    if (dg < 24 && this.rand() < dt * (dg < 16 ? 1.5 : 0.8)) this.shoot(i, this.rr(0.55, 0.95), 0);
    else if (this.rand() < dt * (0.3 + pr * 3)) this.passBall(i, false, false, null);
    const wx = dirx + ax * 1.6; const wz = dirz + az * 1.6;
    const l = Math.hypot(wx, wz) || 1;
    return [wx / l, wz / l];
  }

  aiOffBall(i, p, sign, teamHas, dt) {
    const b = this.ball;
    let hx = p.hx + R.clamp(b.x * 0.18, -6, 6);
    let hz = p.hz + R.clamp(b.z * 0.15, -5, 5);
    const toward = (x, z) => { const dx = x - p.x; const dz = z - p.z; const l = Math.hypot(dx, dz); return l > 1.0 ? [dx / l, dz / l] : [0, 0]; };
    const rank = this.chaseRank(i);
    if (teamHas === p.team) {
      hx += sign * 9; hz += (p.slot % 2 === 0 ? -6 : 6);
      return toward(hx, hz);
    }
    if (teamHas < 0) {
      if (rank === 0) { const dx = b.x - p.x; const dz = b.z - p.z; const l = Math.hypot(dx, dz) || 1; return [dx / l, dz / l]; }
      return toward(hx, hz);
    }
    const holder = this.players[b.owner];
    if (rank === 0) {
      const dx = holder.x - p.x; const dz = holder.z - p.z; const l = Math.hypot(dx, dz) || 1;
      if (l < 1.6 && p.lock <= 0 && this.rand() < dt * 3) this.tryTackle(i, b.owner, false);
      return [dx / l, dz / l];
    }
    if (rank === 1) { const dx = holder.x - sign * 3 - p.x; const dz = holder.z - p.z; const l = Math.hypot(dx, dz) || 1; return [dx / l, dz / l]; }
    return toward(hx, hz);
  }

  keeperSaves() {
    const b = this.ball;
    if (b.owner >= 0) return;
    for (let i = 0; i < this.players.length; i++) {
      const k = this.players[i];
      if (!k.keeper || k.lock > 0) continue;
      const sign = k.team === 0 ? 1 : -1;
      if (-sign * b.vx <= 0) continue;
      const miss = Math.hypot(b.x - k.x, b.y - 1.0, b.z - k.z);
      if (miss > 1.9 || b.y > 2.7 || b.free < 0.1) continue;
      const spd = Math.hypot(b.vx, b.vy, b.vz);
      if (spd < 10) { b.owner = i; b.vx = b.vy = b.vz = 0; this.say('Keeper claims it.'); return; }
      k.lock = 0.6;
      if (this.rand() < R.saveChance(miss, spd, 1.9)) {
        b.vx = sign * spd * 0.35; b.vy = 3; b.vz = (b.z - k.z) * 4 + this.rr(-3, 3);
        this.setAction(k, 'dive', 0.6);
        this.say('Great save!');
      }
      return;
    }
  }

  autoSwitch(dt) {
    this.switchCd = Math.max(0, this.switchCd - dt);
    if (this.switchCd > 0) return;
    const b = this.ball;
    for (const h of this.humans) {
      if (b.owner === h.ctrl) continue;
      const best = this.nearestOutfield(h.team, b.x, b.z);
      if (best >= 0 && best !== h.ctrl) {
        const dc = Math.hypot(this.players[h.ctrl].x - b.x, this.players[h.ctrl].z - b.z);
        const db = Math.hypot(this.players[best].x - b.x, this.players[best].z - b.z);
        if (db < dc - 2.5 && !this.humans.some((o) => o !== h && o.ctrl === best)) { h.ctrl = best; this.switchCd = 0.6; }
      }
    }
  }

  // ------------------------------------------------------------------ views for the wire
  ctrls(maxSlot = 4) {
    const out = new Array(maxSlot).fill(-1);
    for (const h of this.humans) out[h.slot] = h.ctrl;
    return out;
  }

  playerDtos(prec = 3) {
    const q = (v) => Number(v.toFixed(prec));
    return this.players.map((p) => ({ x: q(p.x), z: q(p.z), vx: q(p.vx), vz: q(p.vz), fx: q(p.fx), fz: q(p.fz), a: p.action }));
  }

  ballDto() {
    const q = (v) => Number(v.toFixed(3)); const b = this.ball;
    return { x: q(b.x), y: q(b.y), z: q(b.z), vx: q(b.vx), vy: q(b.vy), vz: q(b.vz), owner: b.owner };
  }

  snapshot() {
    return {
      tick: this.tick, size: TEAM, clock: Number(this.clock.toFixed(2)), score: this.score.slice(),
      phase: this.phase === 'play' ? 1 : 0, half: this.half, ball: this.ballDto(), players: this.playerDtos(),
      ctrls: this.ctrls(), ev: this.feed.slice(), rng: this.rand.getState(), gt: Number((this.tick * DT).toFixed(3)),
      inputs: this.inputLog.slice(-8),
    };
  }

  // Everything needed to rebuild this match elsewhere (resume).
  fullState() {
    return Object.assign(this.snapshot(), {
      players: this.players.map((p) => ({
        x: p.x, z: p.z, vx: p.vx, vz: p.vz, fx: p.fx, fz: p.fz, a: p.action, lock: p.lock, keeper: p.keeper, team: p.team, slot: p.slot,
      })),
      ball: Object.assign(this.ballDto(), { free: this.ball.free, last: this.ball.last }),
    });
  }

  // For determinism tests.
  hash() {
    let h = 2166136261;
    const mix = (v) => { h ^= Math.round(v * 1000) | 0; h = Math.imul(h, 16777619) >>> 0; };
    for (const p of this.players) { mix(p.x); mix(p.z); }
    mix(this.ball.x); mix(this.ball.y); mix(this.ball.z); mix(this.score[0] * 7 + this.score[1]);
    return h >>> 0;
  }
}

module.exports = { Match, HALF_L, HALF_W, GOAL_W, GOAL_H, BALL_R, TEAM, DT, mulberry32 };
