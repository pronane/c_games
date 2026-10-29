// Deterministic fight step. No DOM, no Date, no Math.random.
// Both browsers import this module and advance only when both players'
// inputs for that frame are present.

export const SIM_HZ = 60;
export const SIM_DT = 1 / 60;
export const DEFAULT_DELAY = 3;
export const HASH_EVERY = 30;
export const SCREEN_W = 1280;
export const GROUND_Y = 560;

const SPEED = 240;
const JUMP = -520;
const GRAV = 1600;
const DUR = {
  idle: 6, walk: 4, crouch: 8, jump: 5, lp: 3, hp: 4, lk: 3, hk: 4,
  block: 8, throw: 4, hit: 5, special1: 4, special2: 3, super: 4, win: 6, lose: 8,
};
const DMG = { lp: 6, hp: 12, lk: 7, hk: 11, throw: 14, special1: 15, special2: 16, super: 28 };
const ATTACKS = ['lp', 'hp', 'lk', 'hk', 'throw', 'special1', 'special2', 'super'];

export function neutralInput() {
  return {
    left: false, right: false, up: false, down: false, jump: false,
    lp: false, hp: false, lk: false, hk: false, block: false, throw: false,
    special1: false, special2: false, super: false,
  };
}

export function cloneInput(inp) {
  const n = neutralInput();
  if (!inp) return n;
  for (const k of Object.keys(n)) n[k] = !!inp[k];
  return n;
}

// mulberry32. Returns a float in [0, 1). Both engines step it the same way.
export function makeRng(seed) {
  let a = (Number(seed) >>> 0) || 1;
  return function rng() {
    a |= 0;
    a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function q(n) {
  return Math.round(n * 256) / 256;
}

function frameCount(table, char, state) {
  const row = table && table[char] && table[char][state];
  if (Array.isArray(row) && row[1] > 0) return row[1];
  return 5;
}

function intersect(a, b) {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}

function makeFighter(char, x, facing, frames) {
  return {
    char,
    x,
    y: GROUND_Y,
    vx: 0,
    vy: 0,
    facing,
    state: 'idle',
    frame: 0,
    tick: 0,
    lock: 0,
    hp: 100,
    super: 0,
    blocking: false,
    hitStun: 0,
    combo: 0,
    hitLanded: false,
    frames,
  };
}

function setState(f, s, lockTicks = 0) {
  if (f.state === s && lockTicks === 0) return;
  if (f.state !== s) f.hitLanded = false;
  f.state = s;
  f.frame = 0;
  f.tick = 0;
  f.lock = lockTicks;
}

function inputToState(f, inp, other) {
  if (f.hitStun > 0 || f.lock > 0) return;
  if (inp.throw && Math.abs(f.x - other.x) < 70) { setState(f, 'throw', 18); return; }
  if (inp.lp) { setState(f, 'lp', 12); return; }
  if (inp.hp) { setState(f, 'hp', 16); return; }
  if (inp.lk) { setState(f, 'lk', 12); return; }
  if (inp.hk) { setState(f, 'hk', 16); return; }
  if (inp.special1) { setState(f, 'special1', 18); return; }
  if (inp.special2) { setState(f, 'special2', 18); return; }
  if (inp.super && f.super >= 100) { setState(f, 'super', 24); f.super = 0; return; }
  if (inp.block) { setState(f, 'block', 8); f.blocking = true; return; }
  f.blocking = false;
  let mv = 0;
  if (inp.left) mv -= 1;
  if (inp.right) mv += 1;
  if (mv !== 0) {
    f.vx = mv * SPEED;
    if (f.state !== 'walk' && f.y >= GROUND_Y) setState(f, 'walk');
    f.facing = mv > 0 ? 1 : -1;
  } else {
    f.vx = 0;
    if (f.state === 'walk') setState(f, 'idle');
  }
  if (inp.jump && f.y >= GROUND_Y) { f.vy = JUMP; setState(f, 'jump'); }
  if (inp.down && f.y >= GROUND_Y) setState(f, 'crouch');
}

function updateFighter(f, other) {
  if (f.hitStun > 0) f.hitStun -= 1;
  if (f.lock > 0) {
    f.lock -= 1;
    if (f.lock <= 0 && f.state !== 'jump' && f.state !== 'hit') setState(f, 'idle');
  }
  f.x = q(f.x + f.vx * SIM_DT);
  if (f.y < GROUND_Y || f.vy !== 0) {
    f.y = q(f.y + f.vy * SIM_DT);
    f.vy = q(f.vy + GRAV * SIM_DT);
    if (f.y >= GROUND_Y) {
      f.y = GROUND_Y;
      f.vy = 0;
      if (f.state === 'jump') setState(f, 'idle');
    }
  }
  f.x = Math.max(70, Math.min(SCREEN_W - 70, f.x));
  if (Math.abs(f.x - other.x) > 10) f.facing = other.x > f.x ? 1 : -1;
  f.tick += 1;
  const need = DUR[f.state] || 4;
  if (f.tick >= need) {
    f.tick = 0;
    f.frame += 1;
    const maxF = frameCount(f.frames, f.char, f.state);
    if (f.frame >= maxF) {
      if (ATTACKS.includes(f.state) || f.state === 'hit') setState(f, 'idle');
      else f.frame = 0;
    }
  }
  if (f.state === 'idle' || f.state === 'walk') f.super = q(Math.min(100, f.super + 0.06));
}

function hitbox(f) {
  const s = f.state;
  if (!ATTACKS.includes(s)) return null;
  if (f.hitLanded) return null;
  if (!(f.frame >= 1 && f.frame <= 2)) return null;
  const range = s === 'hp' || s === 'hk' || s === 'super' ? 110 : 78;
  const xoff = f.facing > 0 ? 20 : -20 - range;
  return { x: f.x + xoff, y: f.y - 95, w: range, h: 34, dmg: DMG[s] || 8 };
}

function hurtbox(f) {
  return { x: f.x - 36, y: f.y - 110, w: 72, h: 110 };
}

function takeHit(f, dmg, from) {
  if (f.blocking) {
    f.hitStun = 4;
    f.vx = (f.x > from.x ? 1 : -1) * 60;
    return;
  }
  f.hp = Math.max(0, f.hp - dmg);
  f.hitStun = 10;
  setState(f, 'hit', 10);
  f.vx = (f.x > from.x ? 1 : -1) * 90;
  if (f.hp <= 0) setState(f, 'lose');
}

export function hashMatch(sim) {
  const parts = [sim.frame, sim.timer, sim.hitstop, sim.roll >>> 0, sim.result || '', sim.winner];
  for (const f of sim.fighters) {
    parts.push(
      f.char, f.x, f.y, f.vx, f.vy, f.facing, f.state, f.frame, f.hp,
      f.hitStun, f.lock, f.super, f.blocking ? 1 : 0, f.hitLanded ? 1 : 0, f.combo,
    );
  }
  const s = parts.join('|');
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export function createMatch({ p0, p1, seed, delay, frames }) {
  const rng = makeRng(seed);
  const sim = {
    fighters: [
      makeFighter(p0, 360, 1, frames || null),
      makeFighter(p1, SCREEN_W - 360, -1, frames || null),
    ],
    inputs: [new Map(), new Map()],
    frame: 0,
    timer: 99,
    hitstop: 0,
    delay: delay > 0 ? delay : DEFAULT_DELAY,
    rng,
    roll: 0,
    result: null,
    winner: -1,
    closed: false,
    hits: [],
  };

  sim.setInput = function setInput(player, frame, inp) {
    if (player !== 0 && player !== 1) return false;
    if (typeof frame !== 'number' || frame < 0) return false;
    if (sim.inputs[player].has(frame)) return false;
    sim.inputs[player].set(frame, cloneInput(inp));
    return true;
  };

  sim.canStep = function canStep() {
    return !sim.result && sim.inputs[0].has(sim.frame) && sim.inputs[1].has(sim.frame);
  };

  sim.step = function step() {
    if (sim.result) return false;
    if (!sim.canStep()) return false;
    const i0 = sim.inputs[0].get(sim.frame);
    const i1 = sim.inputs[1].get(sim.frame);
    // One seeded roll per frame so both sims consume the RNG together.
    sim.roll = Math.floor(sim.rng() * 0x100000000);
    if (sim.hitstop > 0) {
      sim.hitstop -= 1;
    } else {
      const a = sim.fighters[0];
      const b = sim.fighters[1];
      inputToState(a, i0, b);
      inputToState(b, i1, a);
      updateFighter(a, b);
      updateFighter(b, a);
      const aHit = hitbox(a);
      const bHit = hitbox(b);
      if (aHit && intersect(aHit, hurtbox(b))) {
        a.hitLanded = true;
        takeHit(b, aHit.dmg, a);
        if (!b.blocking) b.combo += 1;
        sim.hitstop = 4;
        sim.hits.push({ x: q(aHit.x + aHit.w / 2), y: q(aHit.y + 8), t: 0.18 });
      }
      if (bHit && intersect(bHit, hurtbox(a))) {
        b.hitLanded = true;
        takeHit(a, bHit.dmg, b);
        if (!a.blocking) a.combo += 1;
        sim.hitstop = 4;
        sim.hits.push({ x: q(bHit.x + bHit.w / 2), y: q(bHit.y + 8), t: 0.18 });
      }
      if ((a.hp <= 0 || b.hp <= 0) && !sim.result) {
        sim.result = 'ko';
        sim.winner = a.hp > b.hp ? 0 : 1;
      }
    }
    for (const h of sim.hits) h.t = q(h.t - SIM_DT);
    sim.hits = sim.hits.filter((h) => h.t > 0);
    sim.frame += 1;
    if (!sim.result && sim.frame % SIM_HZ === 0) {
      sim.timer = Math.max(0, sim.timer - 1);
      if (sim.timer <= 0) {
        sim.result = 'time';
        sim.winner = sim.fighters[0].hp > sim.fighters[1].hp ? 0 : 1;
      }
    }
    // Drop inputs we will never read again.
    if (sim.frame > 2) {
      sim.inputs[0].delete(sim.frame - 2);
      sim.inputs[1].delete(sim.frame - 2);
    }
    return true;
  };

  sim.hash = function hash() { return hashMatch(sim); };
  return sim;
}
