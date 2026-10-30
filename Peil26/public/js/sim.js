// Real-time match. Speeds are athletic on purpose: the old build felt stuck
// because players barely moved and the camera sat a mile away.

export const PITCH_L = 145;
export const PITCH_W = 90;
export const CZ = 45;
export const GOAL_W = 3.25;
export const BAR = 2.5;
export const ARC = 40;
export const STEP = 0.78;

const ROLES = ["gk", "rfb", "lfb", "rcb", "lcb", "chb", "rwb", "lwb", "cm", "rmf", "lmf", "rff", "ff", "lff", "chf"];
const HOME = {
  gk: [4.2, 45], rfb: [28, 14], lfb: [28, 76], rcb: [20, 32], lcb: [20, 58],
  chb: [34, 45], rwb: [52, 10], lwb: [52, 80], cm: [64, 45], rmf: [78, 24],
  lmf: [78, 66], rff: [104, 16], ff: [112, 45], lff: [104, 74], chf: [96, 45],
};

export const COUNTIES = [
  { name: "Dublin", short: "DUB", jersey: "#5ca8de", shorts: "#101c40", socks: "#5ca8de", trim: "#e6ecf2" },
  { name: "Kerry", short: "KER", jersey: "#00843a", shorts: "#00602a", socks: "#f2c42a", trim: "#f2c42a" },
  { name: "Galway", short: "GAL", jersey: "#7a1830", shorts: "#ececec", socks: "#7a1830", trim: "#ececec" },
  { name: "Mayo", short: "MAY", jersey: "#107640", shorts: "#b01c24", socks: "#b01c24", trim: "#b01c24" },
  { name: "Armagh", short: "ARM", jersey: "#e8761c", shorts: "#ececec", socks: "#e8761c", trim: "#ececec" },
  { name: "Tyrone", short: "TYR", jersey: "#ececec", shorts: "#b01c24", socks: "#b01c24", trim: "#b01c24" },
  { name: "Donegal", short: "DON", jersey: "#f2c42a", shorts: "#00602a", socks: "#00602a", trim: "#00602a" },
  { name: "Cork", short: "COR", jersey: "#b01c24", shorts: "#ececec", socks: "#b01c24", trim: "#ececec" },
  { name: "Derry", short: "DER", jersey: "#b01c24", shorts: "#b01c24", socks: "#ececec", trim: "#ececec" },
  { name: "Down", short: "DOW", jersey: "#b01c24", shorts: "#121212", socks: "#121212", trim: "#121212" },
  { name: "Roscommon", short: "ROS", jersey: "#1c4696", shorts: "#f2ce46", socks: "#1c4696", trim: "#f2ce46" },
  { name: "Monaghan", short: "MON", jersey: "#ececec", shorts: "#121212", socks: "#1c4696", trim: "#1c4696" },
  { name: "Meath", short: "MEA", jersey: "#007634", shorts: "#005628", socks: "#f2c42a", trim: "#141414" },
  { name: "Kildare", short: "KIL", jersey: "#ececec", shorts: "#ececec", socks: "#ececec", trim: "#141414" },
  { name: "Clare", short: "CLA", jersey: "#1c4ea0", shorts: "#d6962a", socks: "#d6962a", trim: "#d6962a" },
  { name: "Louth", short: "LOU", jersey: "#b01c24", shorts: "#b01c24", socks: "#ececec", trim: "#121212" },
];

const FIRST = ["Sean", "Cillian", "Conor", "Padraig", "Darragh", "Oisin", "Tadhg", "Eoin", "Brian", "Niall", "Cathal", "Diarmuid", "Fionn", "Rian", "Liam", "Ciaran", "Shane", "Enda", "Colm", "Aidan", "Kevin", "Jack", "Cormac", "Dara", "Eoghan", "Cian", "Rory", "Evan", "Lorcan", "Mark"];
const LAST = ["Murphy", "Kelly", "Walsh", "Byrne", "Ryan", "Doyle", "Gallagher", "Kennedy", "Lynch", "Murray", "Quinn", "Moore", "Carroll", "Dunne", "Brennan", "Foley", "Hayes", "Griffin", "Healy", "Power", "Nugent", "Sweeney", "Keane", "Brosnan", "McGrath", "Daly", "Flynn", "Reilly", "Horan", "Donnelly"];

function mulberry(seed) {
  let s = seed >>> 0;
  return () => {
    s = (s + 0x6d2b79f5) >>> 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const dist = (x, z, x2, z2) => Math.hypot(x - x2, z - z2);

export function countyByName(name) {
  return COUNTIES.find((c) => c.name === name || c.short === name) || COUNTIES[0];
}

export function createMatch(opts = {}) {
  const rng = mulberry(opts.seed || 26);
  const home = countyByName(opts.home || "Dublin");
  const away = countyByName(opts.away || "Kerry");
  const teams = [side(home), side(away)];
  const players = [];
  let n = 1;
  for (let t = 0; t < 2; t++) {
    const sign = t === 0 ? 1 : -1;
    ROLES.forEach((role, i) => {
      const base = HOME[role];
      const x = t === 0 ? base[0] : PITCH_L - base[0];
      const z = base[1] + (rng() - 0.5) * 1.2;
      players.push({
        id: players.length,
        team: t,
        role,
        number: n++,
        name: `${FIRST[(i + t * 7) % FIRST.length]} ${LAST[(i * 3 + t * 5) % LAST.length]}`,
        x, z, vx: 0, vz: 0, facing: sign > 0 ? 0 : Math.PI,
        on: true, bin: 0, sent: false,
        steps: 0, bounced: false, soloed: false, carry: 0,
        stamina: 1, cd: 0, anim: "idle", kickT: 0, homeX: x, homeZ: z,
      });
    });
  }
  const m = {
    teams, players, rng,
    humanTeam: opts.humanTeam ?? 0,
    controlled: 0,
    difficulty: opts.difficulty || "medium",
    halfMinutes: opts.halfMinutes || 8,
    timeScale: opts.timeScale || 8,
    clock: 0, half: 1, period: "First half",
    phase: "countdown", phaseT: 1.1,
    setKind: null, setTeam: 0, setX: PITCH_L / 2, setZ: CZ,
    ball: { x: PITCH_L / 2, y: 1.4, z: CZ, vx: 0, vy: 0, vz: 0, holder: null, lastKick: null, kicker: null, kickerTeam: null, kickDist: 0, kickType: null, touched: false, released: -1 },
    banner: "THROW-IN", bannerKind: "info", bannerT: 1.1, bannerSub: "",
    hint: "WASD move   Space kick   Q hand   F solo",
    charge: 0, sfx: [],
    shape: [4, 3],
    hooter: false,
    celebrate: 0,
    auto: opts.humanTeam == null,
  };
  m.controlled = players.find((p) => p.team === (m.humanTeam ?? 0) && p.role === "chf").id;
  if (opts.live) {
    m.phase = "open";
    m.bannerT = 0;
    const mid = players.find((p) => p.team === 0 && p.role === "cm");
    claim(m, mid);
  }
  return m;
}

function side(c) {
  return { ...c, goals: 0, points: 0, twos: 0, wides: 0, score() { return `${this.goals}-${String(this.points).padStart(2, "0")}`; }, total() { return this.goals * 3 + this.points; } };
}

export function attackSign(team) { return team === 0 ? 1 : -1; }
export function attackGoal(team) { return team === 0 ? PITCH_L : 0; }
export function ownGoal(team) { return team === 0 ? 0 : PITCH_L; }

function claim(m, p) {
  if (!p || !p.on || p.sent || p.bin > 0) return;
  if (m.ball.holder != null) {
    const cur = m.players[m.ball.holder];
    if (cur) cur.anim = "idle";
  }
  m.ball.holder = p.id;
  m.ball.vx = m.ball.vy = m.ball.vz = 0;
  m.ball.y = 1.15;
  m.ball.x = p.x + Math.cos(p.facing) * 0.42;
  m.ball.z = p.z + Math.sin(p.facing) * 0.42;
  p.steps = 0;
  p.bounced = false;
  p.soloed = false;
  p.carry = 0;
  p.anim = "catch";
  p.kickT = 0.25;
}

function release(m, p, vx, vy, vz, type) {
  p.anim = type === "hand" || type === "fist" ? "hand" : type === "solo" ? "solo" : "kick";
  p.kickT = 0.42;
  p.cd = 0.28;
  m.ball.holder = null;
  m.ball.x = p.x + Math.cos(p.facing) * 0.45;
  m.ball.z = p.z + Math.sin(p.facing) * 0.45;
  m.ball.y = type === "hand" || type === "fist" ? 1.35 : 0.7;
  m.ball.vx = vx; m.ball.vy = vy; m.ball.vz = vz;
  m.ball.kicker = p.id;
  m.ball.kickerTeam = p.team;
  m.ball.kickType = type;
  m.ball.kickDist = Math.abs(attackGoal(p.team) - p.x);
  m.ball.touched = false;
  m.ball.released = m.clock;
  m.sfx.push(type === "hand" || type === "fist" ? "hand" : "kick");
}

function say(m, text, kind = "info", sub = "", time = 1.3, sfx = null) {
  m.banner = text;
  m.bannerKind = kind;
  m.bannerSub = sub;
  m.bannerT = time;
  if (sfx) m.sfx.push(sfx);
}

export function step(m, dt, input) {
  m.sfx.length = 0;
  const scaled = m.phase === "open" || m.phase === "countdown" ? dt * (m.phase === "open" ? m.timeScale : 1) : dt;
  if (m.phase === "open") m.clock += dt * m.timeScale;
  m.bannerT = Math.max(0, m.bannerT - dt);
  m.players.forEach((p) => {
    p.cd = Math.max(0, p.cd - dt);
    p.kickT = Math.max(0, p.kickT - dt);
    if (p.bin > 0) {
      p.bin = Math.max(0, p.bin - dt * m.timeScale);
      if (p.bin === 0) { p.on = true; say(m, `${p.number} RETURNS`, "info", "", 1.1); }
    }
    if (p.stamina < 1) p.stamina = Math.min(1, p.stamina + dt * 0.04);
  });

  if (m.phase === "countdown") {
    m.phaseT -= dt;
    if (m.phaseT <= 0) {
      m.phase = "open";
      m.ball.vy = 6.5;
      m.ball.vx = (m.rng() - 0.5) * 2;
      m.sfx.push("whistle");
    }
    return;
  }
  if (m.phase === "celebrate") {
    m.celebrate -= dt;
    if (m.celebrate <= 0) beginKickout(m, 1 - m.setTeam);
    return;
  }
  if (m.phase === "halftime" || m.phase === "fulltime" || m.phase === "extra") {
    if (input.confirm && m.phase === "halftime") startHalf(m, 2);
    if (input.confirm && m.phase === "extra") startHalf(m, 3);
    if (input.cancel && m.phase === "extra") { m.phase = "fulltime"; say(m, "FULL TIME", "full", "", 8); }
    return;
  }
  if (m.phase === "set") {
    const taker = m.players.find((p) => p.team === m.setTeam && p.on && !p.sent && p.role !== "gk") || m.players.find((p) => p.team === m.setTeam && p.on);
    if (taker) {
      taker.x += (m.setX - taker.x) * Math.min(1, dt * 6);
      taker.z += (m.setZ - taker.z) * Math.min(1, dt * 6);
      if (!m.ball.holder) claim(m, taker);
      const human = m.humanTeam === m.setTeam && !m.auto;
      if (human && input.toArc && m.setKind === "free") {
        const gx = attackGoal(m.setTeam);
        const sign = attackSign(m.setTeam);
        m.setX = gx - sign * ARC;
        m.setZ = CZ;
      }
      if (!human && m.phaseT < 0.2) input = { ...input, kickPressed: true, kickReleased: true, aimHigh: true };
      if (human ? (input.kickReleased || input.kickPressed) : m.phaseT < 0.15) {
        const power = human ? Math.max(0.55, m.charge) : 0.72;
        strike(m, taker, input, power, m.setKind === "penalty" ? "penalty" : "punt");
        m.phase = "open";
        m.charge = 0;
      }
    }
    m.phaseT -= dt;
    tickHumans(m, dt, input, true);
    return;
  }

  tickBall(m, dt);
  tickHumans(m, dt, input, false);
  tickAI(m, dt);
  tickCarry(m, dt);
  tickContest(m);
  tickBounds(m);
  tickShape(m);
  if (m.phase === "open" && m.clock >= m.halfMinutes * 60 && !m.hooter) {
    m.hooter = true;
    m.sfx.push("hooter");
    if (!m.ball.holder && m.ball.y > 0.4 && Math.hypot(m.ball.vx, m.ball.vz) > 6) {
      say(m, "HOOTER", "hooter", "Score in flight can stand", 1.4, null);
    } else {
      endHalf(m);
    }
  }
}

function tickHumans(m, dt, input, frozen) {
  if (m.auto || m.humanTeam == null) return;
  const p = m.players[m.controlled];
  if (!p || !p.on) return;
  const mx = input.moveX || 0;
  const mz = input.moveZ || 0;
  const moving = Math.hypot(mx, mz) > 0.12;
  if (!frozen && p.id !== m.ball.holder) {
    // still allow movement off the ball
  }
  if (!frozen || p.id === m.ball.holder) {
    const sprint = input.sprint && p.stamina > 0.08;
    const target = sprint ? 10.4 : 7.6;
    if (moving) {
      const len = Math.hypot(mx, mz);
      const dvx = (mx / len) * target;
      const dvz = (mz / len) * target;
      p.vx += (dvx - p.vx) * Math.min(1, dt * 14);
      p.vz += (dvz - p.vz) * Math.min(1, dt * 14);
      p.facing = Math.atan2(dvz, dvx);
      if (sprint) p.stamina = Math.max(0, p.stamina - dt * 0.08);
    } else {
      p.vx *= Math.exp(-10 * dt);
      p.vz *= Math.exp(-10 * dt);
    }
    p.x = clamp(p.x + p.vx * dt, -1, PITCH_L + 1);
    p.z = clamp(p.z + p.vz * dt, -1, PITCH_W + 1);
    const sp = Math.hypot(p.vx, p.vz);
    if (p.kickT <= 0) p.anim = sp > 7.3 ? "run" : sp > 0.8 ? "run" : "idle";
  }
  if (input.switch) switchPlayer(m);
  if (p.id === m.ball.holder && m.phase === "open") {
    if (input.kickHeld) m.charge = Math.min(1, m.charge + dt / 0.32);
    if (input.hand) pass(m, p, input, "hand");
    else if (input.fist) pass(m, p, input, "fist");
    else if (input.solo) solo(m, p);
    else if (input.bounce) bounce(m, p);
    else if (input.hook) strike(m, p, input, Math.max(0.6, m.charge), "hook");
    else if (input.kickReleased) {
      strike(m, p, input, m.charge > 0.12 ? m.charge : 0.62, "punt");
      m.charge = 0;
    }
  } else {
    m.charge = input.kickHeld ? m.charge : 0;
    if (input.tackle) tackle(m, p);
    if (input.block) p.anim = "block";
    if (input.sidestep) { p.vx += Math.cos(p.facing + 1.2) * 4; p.vz += Math.sin(p.facing + 1.2) * 4; }
    if (input.mark) tryMark(m, p);
  }
  if (input.aim) p.facing = Math.atan2(input.aim.z - p.z, input.aim.x - p.x);
  m.hint = padHint(input, p, m);
}

function padHint(input, p, m) {
  if (m.phase === "set") return m.setKind === "free" ? "FREE  ·  hold kick, release  ·  Y to the arc" : `${(m.setKind || "KICK").toUpperCase()}  ·  release to strike`;
  if (p.id === m.ball.holder) return "KICK hold / release    Q hand    F solo    R bounce";
  return "Tackle X / LB    Switch C / Back    Sprint Shift / RB";
}

function switchPlayer(m) {
  const ball = m.ball;
  let best = null;
  let bd = 1e9;
  for (const p of m.players) {
    if (p.team !== m.humanTeam || !p.on || p.sent || p.id === m.controlled) continue;
    const d = dist(p.x, p.z, ball.x, ball.z);
    if (d < bd) { bd = d; best = p; }
  }
  if (best) {
    m.controlled = best.id;
    m.sfx.push("switch");
  }
}

function strike(m, p, input, power, type) {
  if (p.id !== m.ball.holder) return;
  const aim = input.aim || { x: p.x + Math.cos(p.facing) * 20, z: p.z + Math.sin(p.facing) * 20 };
  let tx = aim.x;
  let tz = aim.z;
  const gx = attackGoal(p.team);
  const sign = attackSign(p.team);
  const toward = (tx - p.x) * sign > 1.5;
  const zAt = Math.abs(tx - p.x) > 0.2 ? p.z + ((gx - p.x) / (tx - p.x)) * (tz - p.z) : null;
  const atPosts = zAt != null && Math.abs(zAt - CZ) < 8 && toward;
  const dgoal = Math.abs(gx - p.x);
  const dx = tx - p.x;
  const dz = tz - p.z;
  let len = Math.hypot(dx, dz) || 1;
  let ty = 1.4;
  if (type === "punt" && atPosts && dgoal < 58) {
    tz = clamp(zAt, CZ - 2.4, CZ + 2.4);
    tx = gx + sign * 2.6;
    const high = input.aimHigh !== false;
    ty = high ? 3.9 : 0.85;
    m.teams[p.team].shots = (m.teams[p.team].shots || 0) + 1;
  } else if (type === "hook") ty = 1.6;
  const dx2 = tx - p.x;
  const dz2 = tz - p.z;
  len = Math.hypot(dx2, dz2) || 1;
  const flight = clamp(len / (15 + power * 8), 0.35, 2.4);
  const g = 11.5;
  const vy = (ty - 0.85) / flight + 0.5 * g * flight;
  const speed = (len / flight) * 1.12;
  release(m, p, (dx2 / len) * speed, vy, (dz2 / len) * speed, type === "penalty" ? "punt" : type);
  if (type === "hook") m.ball.vx += (m.rng() - 0.5) * 2;
}

function pass(m, p, input, kind) {
  if (p.id !== m.ball.holder) return;
  const aim = input.aim || { x: p.x + Math.cos(p.facing) * 12, z: p.z + Math.sin(p.facing) * 12 };
  const mate = lockMate(m, p, aim.x, aim.z);
  const tx = mate ? mate.x : aim.x;
  const tz = mate ? mate.z : aim.z;
  const dx = tx - p.x;
  const dz = tz - p.z;
  const len = Math.hypot(dx, dz) || 1;
  const speed = kind === "fist" ? 16 : 13;
  release(m, p, (dx / len) * speed, 3.2, (dz / len) * speed, kind);
}

function lockMate(m, p, ax, az) {
  const ang = Math.atan2(az - p.z, ax - p.x);
  let best = null;
  let bang = 0.45;
  for (const o of m.players) {
    if (o.team !== p.team || o.id === p.id || !o.on) continue;
    const d = dist(p.x, p.z, o.x, o.z);
    if (d < 4 || d > 36) continue;
    const a = Math.atan2(o.z - p.z, o.x - p.x);
    let diff = Math.abs(a - ang);
    if (diff > Math.PI) diff = Math.PI * 2 - diff;
    if (diff < bang) { bang = diff; best = o; }
  }
  return best;
}

function solo(m, p) {
  if (p.id !== m.ball.holder || p.steps < 1) return;
  p.soloed = true;
  p.bounced = false;
  p.steps = 0;
  p.anim = "solo";
  p.kickT = 0.18;
  m.sfx.push("solo");
}

function bounce(m, p) {
  if (p.id !== m.ball.holder) return;
  if (p.bounced) {
    free(m, 1 - p.team, p.x, p.z, "DOUBLE BOUNCE");
    return;
  }
  p.bounced = true;
  p.steps = Math.max(0, p.steps - 1);
  m.sfx.push("bounce");
}

function tackle(m, p) {
  if (p.cd > 0) return;
  p.cd = 0.45;
  p.anim = "block";
  let best = null;
  let bd = 1.7;
  for (const o of m.players) {
    if (o.team === p.team || o.id !== m.ball.holder) continue;
    const d = dist(p.x, p.z, o.x, o.z);
    if (d < bd) { bd = d; best = o; }
  }
  if (!best) return;
  const fromBehind = Math.cos(best.facing) * (p.x - best.x) + Math.sin(best.facing) * (p.z - best.z) < -0.75;
  if (fromBehind) {
    const nearGoal = Math.abs(attackGoal(best.team) - best.x) < 20;
    free(m, best.team, best.x, best.z, nearGoal ? "PENALTY" : "PULL DOWN");
    if (nearGoal) {
      m.setKind = "penalty";
      m.setX = attackGoal(best.team) - attackSign(best.team) * 11;
      m.setZ = CZ;
      card(m, p, "black");
    }
    return;
  }
  m.ball.holder = null;
  m.ball.y = 0.8;
  m.ball.vx = Math.cos(p.facing) * 4;
  m.ball.vz = Math.sin(p.facing) * 4;
  m.ball.vy = 2;
  m.ball.released = m.clock;
  m.sfx.push("tackle");
}

function tryMark(m, p) {
  if (m.ball.holder != null || m.ball.y < 1.2) return;
  if (dist(p.x, p.z, m.ball.x, m.ball.z) > 1.4) return;
  if (m.ball.kickType === "hand" || m.ball.kickType === "fist") return;
  claim(m, p);
  say(m, "MARK", "point", p.name, 1.2, "whistle");
  m.phase = "set";
  m.setKind = "mark";
  m.setTeam = p.team;
  m.setX = p.x;
  m.setZ = p.z;
  m.phaseT = 4;
}

function tickAI(m, dt) {
  for (const p of m.players) {
    if (!p.on || p.sent) continue;
    if (!m.auto && p.team === m.humanTeam && p.id === m.controlled) continue;
    const sign = attackSign(p.team);
    const gx = attackGoal(p.team);
    const b = m.ball;
    let tx = p.homeX;
    let tz = p.homeZ;
    let sprint = false;
    if (b.holder === p.id) {
      const dgoal = Math.abs(gx - p.x);
      const zOff = Math.abs(p.z - CZ);
      if (p.role === "gk") {
        tx = ownGoal(p.team) + sign * 8;
        tz = CZ;
        if (p.cd <= 0 && p.carry > 0.35) {
          strike(m, p, { aim: { x: PITCH_L / 2 + sign * 20, z: CZ + (m.rng() - 0.5) * 18 }, aimHigh: true }, 0.8, "punt");
        }
      } else if (dgoal < 38 && zOff > 7) {
        tx = gx - sign * 14;
        tz = CZ;
        sprint = true;
      } else {
        tx = gx - sign * 8;
        tz = CZ + (p.homeZ - CZ) * 0.25;
        sprint = dgoal > 30;
      }
      if (p.role !== "gk" && p.cd <= 0 && m.phase === "open") {
        if (dgoal < 24 && zOff < 11) {
          strike(m, p, { aim: { x: gx + sign * 2.6, z: CZ }, aimHigh: false }, 0.84, "punt");
        } else if (dgoal < 55 && zOff < 16) {
          strike(m, p, { aim: { x: gx + sign * 2.6, z: CZ }, aimHigh: true }, 0.78, "punt");
        } else if (p.carry > 0.85) {
          const mate = m.players.find((o) => o.team === p.team && o.on && o.id !== p.id && Math.abs(attackGoal(p.team) - o.x) < dgoal - 6);
          if (mate) pass(m, p, { aim: { x: mate.x, z: mate.z } }, "hand");
          else if (p.steps > 3.1) solo(m, p);
        }
      }
    } else if (p.role === "gk") {
      tx = ownGoal(p.team) + sign * 1.3;
      tz = clamp(CZ + (b.z - CZ) * 0.45, CZ - 3.2, CZ + 3.2);
    } else if (b.holder == null) {
      const d = dist(p.x, p.z, b.x, b.z);
      if (d < 18 && p.role !== "gk") {
        tx = b.x;
        tz = b.z;
        sprint = d > 6;
      }
    } else {
      const holder = m.players[b.holder];
      if (holder && holder.team !== p.team && dist(p.x, p.z, holder.x, holder.z) < 10 && p.role !== "gk") {
        tx = holder.x;
        tz = holder.z;
        sprint = true;
        if (dist(p.x, p.z, holder.x, holder.z) < 1.35 && p.cd <= 0 && m.rng() < 0.012) tackle(m, p);
      } else {
        // sag toward the ball but keep a shape
        tx = p.homeX * 0.55 + b.x * 0.45;
        tz = p.homeZ * 0.7 + b.z * 0.3;
      }
    }
    steer(p, tx, tz, sprint, dt);
  }
}

function steer(p, tx, tz, sprint, dt) {
  const dx = tx - p.x;
  const dz = tz - p.z;
  const d = Math.hypot(dx, dz) || 1;
  const target = sprint && p.stamina > 0.05 ? 10.2 : 7.5;
  if (d < 0.55) {
    p.vx *= Math.exp(-8 * dt);
    p.vz *= Math.exp(-8 * dt);
  } else {
    p.vx += ((dx / d) * target - p.vx) * Math.min(1, dt * 10);
    p.vz += ((dz / d) * target - p.vz) * Math.min(1, dt * 10);
    p.facing = Math.atan2(dz, dx);
  }
  p.x = clamp(p.x + p.vx * dt, -2, PITCH_L + 2);
  p.z = clamp(p.z + p.vz * dt, -2, PITCH_W + 2);
  const sp = Math.hypot(p.vx, p.vz);
  if (p.kickT <= 0) p.anim = sp > 1.1 ? "run" : "idle";
  if (sprint) p.stamina = Math.max(0, p.stamina - dt * 0.05);
}

function tickCarry(m, dt) {
  const id = m.ball.holder;
  if (id == null) return;
  const p = m.players[id];
  const moved = dist(p._px ?? p.x, p._pz ?? p.z, p.x, p.z);
  p._px = p.x;
  p._pz = p.z;
  m.ball.x = p.x + Math.cos(p.facing) * 0.42;
  m.ball.z = p.z + Math.sin(p.facing) * 0.42;
  m.ball.y = 1.15 + Math.sin(m.clock * 8) * 0.03;
  p.carry += dt;
  p.steps += Math.min(moved, 0.45) / STEP;
  if (p.steps > 2.8 && (m.auto || p.team !== m.humanTeam)) solo(m, p);
  if (p.steps > 4.2) {
    free(m, 1 - p.team, p.x, p.z, "OVERCARRY");
  }
}

function tickBall(m, dt) {
  if (m.ball.holder != null) return;
  const b = m.ball;
  b.vy -= 11.5 * dt;
  b.x += b.vx * dt;
  b.y += b.vy * dt;
  b.z += b.vz * dt;
  const drag = Math.exp(-0.045 * dt);
  b.vx *= drag;
  b.vz *= drag;
  if (b.y < 0.12) {
    b.y = 0.12;
    if (Math.abs(b.vy) > 2.2) {
      b.vy = -b.vy * 0.42;
      m.sfx.push("bounce");
    } else b.vy = 0;
    b.vx *= 0.86;
    b.vz *= 0.86;
  }
}

function tickContest(m) {
  const b = m.ball;
  if (b.holder != null) return;
  const speed = Math.hypot(b.vx, b.vy, b.vz);
  const age = m.clock - b.released;
  // A strike has to leave the foot. Do not let a shoulder catch it on the way out.
  if (age < 0.32 && speed > 8) return;
  if (speed > 11 && b.y > 0.8 && b.vy > -0.5) return;
  if (b.y > 2.3) return;
  let best = null;
  let bd = 1.05;
  for (const p of m.players) {
    if (!p.on || p.sent) continue;
    if (p.id === b.kicker && age < 0.55) continue;
    const d = dist(p.x, p.z, b.x, b.z);
    if (d < bd && b.y < 1.85) { bd = d; best = p; }
  }
  if (best) {
    if (b.kickerTeam === best.team) b.touched = true;
    claim(m, best);
    if (best.team !== m.humanTeam) best.anim = "catch";
  }
}

function tickBounds(m) {
  const b = m.ball;
  if (b.holder != null) return;
  if (b.x < 0 || b.x > PITCH_L) {
    const end = b.x < 0 ? 0 : PITCH_L;
    const attacking = end === PITCH_L ? 0 : 1;
    const defending = 1 - attacking;
    const kickerTeam = b.kickerTeam;
    const between = Math.abs(b.z - CZ) <= GOAL_W - 0.05;
    const over = b.y > BAR && b.y < 15 && between;
    const under = b.y <= BAR && b.y >= 0 && between;
    if (kickerTeam === attacking && under && b.kickType !== "hand") {
      if (!save(m, defending)) score(m, attacking, "goal");
      return;
    }
    if (kickerTeam === attacking && under && (b.kickType === "fist" || b.kickType === "hand")) {
      if (!save(m, defending)) score(m, attacking, "goal");
      return;
    }
    if (kickerTeam === attacking && over && b.kickType !== "hand") {
      const two = b.kickDist >= ARC - 0.2 && !b.touched && b.kickType !== "45" && b.kickType !== "sideline" && b.kickType !== "fist";
      score(m, attacking, two ? "two" : "point");
      return;
    }
    if (kickerTeam === defending) {
      award45(m, attacking, end);
      return;
    }
    m.teams[attacking].wides++;
    say(m, "WIDE", "info", "", 1.1, "groan");
    beginKickout(m, defending);
    return;
  }
  if (b.z < 0 || b.z > PITCH_W) {
    const team = b.kickerTeam == null ? 0 : 1 - b.kickerTeam;
    m.phase = "set";
    m.setKind = "sideline";
    m.setTeam = team;
    m.setX = clamp(b.x, 8, PITCH_L - 8);
    m.setZ = b.z < 0 ? 1.2 : PITCH_W - 1.2;
    m.phaseT = 1.2;
    b.holder = null;
    b.vx = b.vy = b.vz = 0;
    b.x = m.setX; b.z = m.setZ; b.y = 0.2;
    say(m, "SIDELINE", "info", "", 1.1, "whistle");
  }
}

function save(m, defending) {
  const gk = m.players.find((p) => p.team === defending && p.role === "gk" && p.on);
  if (!gk) return false;
  const end = ownGoal(defending);
  if (Math.abs(gk.x - end) > 4) return false;
  if (Math.abs(gk.z - m.ball.z) > 2.4) return false;
  if (m.ball.y > 1.9) return false;
  if (m.rng() > 0.42) return false;
  m.ball.vx = attackSign(defending) * 8;
  m.ball.vy = 2;
  m.ball.vz = (m.rng() - 0.5) * 4;
  m.ball.x = end + attackSign(defending) * 1.2;
  m.ball.released = m.clock;
  m.ball.kicker = gk.id;
  m.ball.kickerTeam = defending;
  m.ball.kickType = "punt";
  say(m, "SAVE", "info", gk.name, 1.2, "save");
  gk.anim = "block";
  gk.kickT = 0.35;
  return true;
}

function score(m, team, kind) {
  const side = m.teams[team];
  if (kind === "goal") {
    side.goals++;
    say(m, "GOAL", "goal", m.players[m.ball.kicker]?.name || "", 1.7, "goal");
  } else if (kind === "two") {
    side.points += 2;
    side.twos++;
    say(m, "2 POINTS", "two", "From outside the 40", 1.6, "two");
  } else {
    side.points++;
    say(m, "POINT", "point", m.players[m.ball.kicker]?.name || "", 1.45, "point");
  }
  m.phase = "celebrate";
  m.celebrate = kind === "goal" ? 1.7 : 1.35;
  m.setTeam = team;
  m.ball.vx = m.ball.vy = m.ball.vz = 0;
  m.ball.holder = null;
  if (m.hooter) endHalf(m);
}

function award45(m, attacking, end) {
  m.phase = "set";
  m.setKind = "45";
  m.setTeam = attacking;
  m.setX = end === 0 ? 45 : PITCH_L - 45;
  m.setZ = CZ + 10;
  m.phaseT = 1.3;
  m.ball.holder = null;
  m.ball.vx = m.ball.vy = m.ball.vz = 0;
  say(m, "45", "info", "", 1.2, "whistle");
}

function beginKickout(m, defending) {
  m.phase = "set";
  m.setKind = "kickout";
  m.setTeam = defending;
  const sign = attackSign(defending);
  m.setX = ownGoal(defending) + sign * 20;
  m.setZ = CZ;
  m.phaseT = 1.15;
  m.ball.holder = null;
  m.ball.x = m.setX;
  m.ball.z = CZ;
  m.ball.y = 0.2;
  m.ball.vx = m.ball.vy = m.ball.vz = 0;
  if (m.hooter) endHalf(m);
}

function free(m, team, x, z, label) {
  m.phase = "set";
  m.setKind = label === "PENALTY" ? "penalty" : "free";
  m.setTeam = team;
  m.setX = clamp(x, 8, PITCH_L - 8);
  m.setZ = clamp(z, 4, PITCH_W - 4);
  m.phaseT = 1.2;
  m.ball.holder = null;
  m.ball.vx = m.ball.vy = m.ball.vz = 0;
  m.ball.x = m.setX;
  m.ball.z = m.setZ;
  m.ball.y = 0.2;
  say(m, label, label === "PENALTY" ? "penalty" : "info", "", 1.3, "whistle");
}

function card(m, p, kind) {
  if (kind === "black") {
    p.bin = 10 * 60;
    p.on = false;
    say(m, "BLACK CARD", "black", `${p.name}  ·  10 minutes`, 1.6, "whistle");
  }
}

function tickShape(m) {
  for (let t = 0; t < 2; t++) {
    const own = m.players.filter((p) => p.team === t && p.on && (t === 0 ? p.x <= PITCH_L / 2 : p.x >= PITCH_L / 2)).length;
    const opp = m.players.filter((p) => p.team === t && p.on && (t === 0 ? p.x >= PITCH_L - 45 : p.x <= 45)).length;
    if (t === (m.humanTeam ?? 0)) m.shape = [own, opp];
  }
}

function endHalf(m) {
  if (m.half === 1) {
    m.phase = "halftime";
    say(m, "HALF TIME", "full", "Enter for the second half", 30);
  } else {
    const a = m.teams[0].total();
    const b = m.teams[1].total();
    if (a === b && m.half === 2) {
      m.phase = "extra";
      say(m, "LEVEL", "full", "Enter for extra time, Esc to finish", 30);
    } else {
      m.phase = "fulltime";
      say(m, "FULL TIME", "full", "", 30);
    }
  }
}

function startHalf(m, half) {
  m.half = half;
  m.clock = 0;
  m.hooter = false;
  m.period = half === 2 ? "Second half" : "Extra time";
  m.phase = "countdown";
  m.phaseT = 1.0;
  m.ball.x = PITCH_L / 2;
  m.ball.z = CZ;
  m.ball.y = 1.3;
  m.ball.vx = m.ball.vy = m.ball.vz = 0;
  m.ball.holder = null;
  say(m, "THROW-IN", "info", "", 1);
}

export function clockStr(m) {
  const t = Math.floor(m.clock);
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
}

export function controlled(m) {
  return m.players[m.controlled];
}
