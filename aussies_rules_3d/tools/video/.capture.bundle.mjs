// src/rules/types.ts
function totalPoints(s) {
  return s.goals * 6 + s.behinds;
}
var AFL_SETTINGS = {
  quarterSeconds: 20 * 60,
  quarters: 4,
  interchange: 5,
  rotationCap: 75,
  seed: 1,
  difficulty: "afl"
};
var FIELD = {
  /** Superellipse exponent for the boundary shape. */
  shapeN: 2.4,
  /** Boundary semi-axes: x = goal-to-goal, z = wing to wing. */
  boundaryA: 85.5,
  boundaryB: 73,
  /** Goal line distance from centre along x. */
  goalLineX: 69,
  /** Half-distance between the goal posts (6.4 m apart). */
  goalPostHalf: 3.2,
  /** Behind posts sit 6.4 m outside the goal posts. */
  behindPostHalf: 9.6,
  /** Goal square depth (9 m) and half width (= goal post half). */
  goalSquareDepth: 9,
  /** 50 metre arc radius (from the centre of the goal line). */
  arcRadius: 50,
  /** Centre square is 50 m x 50 m. */
  centreSquareHalf: 25,
  /** Centre circle radius (ruck line at centre ball-ups). */
  centreCircleRadius: 10,
  /** Kick must travel at least this far untouched to be a mark. */
  markMinDistance: 15,
  /** Run-with-ball distance before a bounce/touch-down is required. */
  runBounceMetres: 15,
  /** Protected area around the mark (2026 stand rule: 5 m). */
  protectedAreaMetres: 5,
  /** Seconds allowed to bring the ball back into play (mark/free/kick-in). */
  restartSeconds: 8
};

// src/rules/field.ts
function boundaryRadiusAt(angle) {
  const { boundaryA: a, boundaryB: b, shapeN: n } = FIELD;
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  const x = Math.sign(c) * Math.pow(Math.abs(c), 2 / n) * a;
  const y = Math.sign(s) * Math.pow(Math.abs(s), 2 / n) * b;
  return Math.hypot(x, y);
}
function isOutOfBounds(x, z, ballRadius = 0.15) {
  const { boundaryA: a, boundaryB: b, shapeN: n } = FIELD;
  const v = Math.pow(Math.abs(x) / (a + ballRadius), n) + Math.pow(Math.abs(z) / (b + ballRadius), n);
  return v > 1;
}
function attackGoalX(team) {
  return team === 0 ? FIELD.goalLineX : -FIELD.goalLineX;
}
function defendGoalX(team) {
  return -attackGoalX(team);
}
function insideAttackArc(x, z, team) {
  const gx = attackGoalX(team);
  return Math.hypot(x - gx, z) <= FIELD.arcRadius;
}
function betweenArcs(x) {
  return Math.abs(x) < FIELD.goalLineX - FIELD.arcRadius;
}
function scoreAtCrossing(crossX, z) {
  const side = crossX > 0 ? 0 : 1;
  const az = Math.abs(z);
  if (az <= FIELD.goalPostHalf) return { kind: "goal", team: side };
  if (az <= FIELD.behindPostHalf) return { kind: "behind", team: side };
  return null;
}
function boundaryCrossing(x0, z0, x1, z1) {
  let lo = 0;
  let hi = 1;
  for (let i = 0; i < 24; i++) {
    const m = (lo + hi) / 2;
    const x = x0 + (x1 - x0) * m;
    const z = z0 + (z1 - z0) * m;
    if (isOutOfBounds(x, z, 0)) hi = m;
    else lo = m;
  }
  return { x: x0 + (x1 - x0) * hi, z: z0 + (z1 - z0) * hi };
}
function clampInside(x, z, margin = 1) {
  if (!isOutOfBounds(x, z, -margin)) return { x, z };
  const ang = Math.atan2(z, x);
  const r = boundaryRadiusAt(ang) - margin;
  return { x: Math.cos(ang) * r, z: Math.sin(ang) * r };
}

// src/rules/laws.ts
function applyScore(scores, outcome) {
  if (outcome.kind === "goal") scores[outcome.team].goals += 1;
  else if (outcome.kind === "behind") scores[outcome.team].behinds += 1;
  else if (outcome.kind === "goalPost") scores[outcome.behindTeam].behinds += 1;
}
function decideMark(ball, catcher) {
  if (ball.mode !== "held") return { kind: "playOn", reason: "notCaught" };
  if (ball.holderId !== catcher.id) return { kind: "playOn", reason: "notCaught" };
  if (ball.lastDisposal !== "kick") return { kind: "playOn", reason: "notCaught" };
  if (ball.bounced) return { kind: "playOn", reason: "bounced" };
  if (ball.touched) return { kind: "playOn", reason: "touched" };
  if (ball.kickDistance < FIELD.markMinDistance) return { kind: "playOn", reason: "short" };
  return { kind: "mark", team: catcher.team, playerId: catcher.id };
}
function decideTackle(tackler, ballCarrier, ctx) {
  const toTeam = tackler.team;
  if (ctx.highContact) return { kind: "highTackle", againstId: tackler.id, toTeam: ballCarrier.team };
  if (ctx.backContact) return { kind: "pushInTheBack", againstId: tackler.id, toTeam: ballCarrier.team };
  if (ctx.incorrectDisposal) {
    return { kind: "incorrectDisposal", againstId: ballCarrier.id, toTeam };
  }
  if (ctx.priorOpportunity) {
    return { kind: "holdingTheBall", againstId: ballCarrier.id, toTeam };
  }
  if (ctx.ballSpilledFree && ctx.attemptedDisposal) {
    return { kind: "legalTacklePlayOn" };
  }
  return { kind: "noPriorBallUp" };
}
function decideRunTooFar(metresRunWithBall, hasBounced) {
  if (!hasBounced && metresRunWithBall > FIELD.runBounceMetres) {
    return { kind: "freeKick", reason: "runningTooFar" };
  }
  return { kind: "ok" };
}
function decideOutOfBounds(ball, crossX, crossZ, disposeTeam, smotheredOrDeflected, deliberate) {
  const other = disposeTeam === null ? null : disposeTeam === 0 ? 1 : 0;
  if (ball.lastDisposal === "kick" && !ball.bounced && !ball.touched && !smotheredOrDeflected && other !== null) {
    return { kind: "outOnTheFull", toTeam: other, x: crossX, z: crossZ };
  }
  const kickedOrHandballed = ball.lastDisposal === "kick" || ball.lastDisposal === "handball";
  if (kickedOrHandballed && !ball.touched && !smotheredOrDeflected && betweenArcs(crossX) && other !== null) {
    return { kind: "lastDisposal", toTeam: other, x: crossX, z: crossZ };
  }
  if (deliberate && other !== null) {
    return { kind: "deliberate", toTeam: other, x: crossX, z: crossZ };
  }
  return { kind: "throwIn", x: crossX, z: crossZ };
}
function makeFreeKick(team, takerId, x, z, reason, opts = {}) {
  const spot = clampInside(x, z);
  return {
    team,
    takerId,
    x: spot.x,
    z: spot.z,
    reason,
    fiftyMetres: false,
    markX: spot.x,
    markZ: spot.z,
    shotClock: FIELD.restartSeconds,
    isMark: false,
    isSetShot: false,
    ...opts
  };
}
function applyFiftyMetrePenalty(fk) {
  const goalX = attackGoalX(fk.team);
  const dir = Math.sign(goalX - fk.x) || 1;
  let nx = fk.x + dir * 50;
  if (Math.abs(goalX - fk.x) < 50) {
    nx = goalX - dir * FIELD.goalSquareDepth;
  }
  const spot = clampInside(nx, fk.z);
  return {
    ...fk,
    x: spot.x,
    z: spot.z,
    fiftyMetres: true,
    isSetShot: Math.abs(goalX - spot.x) <= FIELD.arcRadius
  };
}
function isSetShot(fk) {
  return Math.abs(attackGoalX(fk.team) - fk.x) <= FIELD.arcRadius;
}

// src/rules/engine.ts
var ROLE_PLAN = [
  "fullback",
  "keyDefender",
  "keyDefender",
  "halfBack",
  "halfBack",
  "halfBack",
  "midfielder",
  "midfielder",
  "midfielder",
  "midfielder",
  "ruck",
  "midfielder",
  "halfForward",
  "halfForward",
  "halfForward",
  "keyForward",
  "keyForward",
  "fullForward"
];
var FIRST_NAMES = [
  "Jack",
  "Tom",
  "Liam",
  "Noah",
  "Oliver",
  "Harry",
  "Cooper",
  "Bailey",
  "Mitch",
  "Luke",
  "Josh",
  "Sam",
  "Will",
  "Charlie",
  "Alex",
  "Max",
  "Ben",
  "Jake",
  "Toby",
  "Oscar",
  "Hugh",
  "Finn",
  "Ned",
  "Rory",
  "Darcy",
  "Jai",
  "Kye",
  "Lockie",
  "Trent",
  "Bailey"
];
var LAST_NAMES = [
  "McKenzie",
  "Kelly",
  "O\u2019Brien",
  "Smith",
  "Jones",
  "Brown",
  "Williams",
  "Wilson",
  "Taylor",
  "Davies",
  "Martin",
  "Anderson",
  "Walker",
  "White",
  "Thompson",
  "Harris",
  "Nelson",
  "Ryan",
  "Bennett",
  "Foster",
  "Grant",
  "Palmer",
  "Walsh",
  "Reid",
  "Mills",
  "Pearce",
  "Chen",
  "Patel",
  "Kowalski",
  "Villa"
];
function statsFor(role, rng) {
  const base = 0.55 + rng() * 0.35;
  const tweak = (v) => Math.min(1, Math.max(0.2, v));
  switch (role) {
    case "ruck":
      return { speed: tweak(base - 0.12), strength: tweak(base + 0.25), kicking: tweak(base - 0.05), marking: tweak(base + 0.2), tackling: tweak(base + 0.1), endurance: tweak(base - 0.1) };
    case "midfielder":
      return { speed: tweak(base + 0.12), strength: tweak(base), kicking: tweak(base + 0.1), marking: tweak(base - 0.05), tackling: tweak(base + 0.08), endurance: tweak(base + 0.2) };
    case "keyForward":
    case "fullForward":
      return { speed: tweak(base), strength: tweak(base + 0.15), kicking: tweak(base + 0.18), marking: tweak(base + 0.22), tackling: tweak(base - 0.05), endurance: tweak(base - 0.05) };
    case "keyDefender":
    case "fullback":
      return { speed: tweak(base), strength: tweak(base + 0.15), kicking: tweak(base + 0.05), marking: tweak(base + 0.18), tackling: tweak(base + 0.12), endurance: tweak(base) };
    default:
      return { speed: tweak(base + 0.08), strength: tweak(base), kicking: tweak(base + 0.12), marking: tweak(base + 0.05), tackling: tweak(base + 0.05), endurance: tweak(base + 0.1) };
  }
}
function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = a + 1831565813 | 0;
    let t = Math.imul(a ^ a >>> 15, 1 | a);
    t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
    return ((t ^ t >>> 14) >>> 0) / 4294967296;
  };
}
function buildRoster(team, seed, bench) {
  const rng = mulberry32(seed * 1e3 + team * 101 + 7);
  const roster = [];
  for (let i = 0; i < 18 + bench; i++) {
    const role = i < 18 ? ROLE_PLAN[i] : "midfielder";
    roster.push({
      name: `${FIRST_NAMES[Math.floor(rng() * FIRST_NAMES.length)]} ${LAST_NAMES[Math.floor(rng() * LAST_NAMES.length)]}`,
      number: i + 1 + team * 20,
      role,
      stats: statsFor(role, rng)
    });
  }
  return roster;
}
var RulesEngine = class {
  state;
  rng;
  possession = {
    holderSince: 0,
    priorOpportunity: false,
    metresSinceBounce: 0,
    shrugOrFend: false
  };
  phaseTimer = 0;
  kickInTimer = 0;
  celebrationIsGoal = false;
  celebrationDefendingTeam = 1;
  constructor(settings2 = AFL_SETTINGS) {
    this.rng = mulberry32(settings2.seed);
    this.state = {
      settings: settings2,
      clock: { quarter: 1, secondsRemaining: settings2.quarterSeconds, running: false, timeOn: 0 },
      scores: [{ goals: 0, behinds: 0 }, { goals: 0, behinds: 0 }],
      ball: this.freshBall(),
      players: [],
      phase: "preMatch",
      freeKick: null,
      restartX: 0,
      restartZ: 0,
      nominatedRucks: [null, null],
      rotations: [0, 0],
      events: [],
      winner: null,
      setShotDeadline: 0
    };
  }
  freshBall() {
    return {
      x: 0,
      y: 0.3,
      z: 0,
      vx: 0,
      vy: 0,
      vz: 0,
      spin: 0,
      mode: "dead",
      holderId: null,
      kickedById: null,
      kickedFromX: 0,
      kickedFromZ: 0,
      kickDistance: 0,
      kickedAt: 0,
      touched: false,
      bounced: false,
      lastDisposal: "none",
      handballedById: null
    };
  }
  // ------------------------------------------------------------------ setup
  buildTeams(rosters) {
    const [home, away] = rosters ?? [
      buildRoster(0, this.state.settings.seed, this.state.settings.interchange),
      buildRoster(1, this.state.settings.seed, this.state.settings.interchange)
    ];
    this.state.players = [];
    for (const team of [0, 1]) {
      const roster = team === 0 ? home : away;
      roster.forEach((entry, i) => {
        this.state.players.push({
          id: team * 100 + i,
          team,
          number: entry.number,
          name: entry.name,
          role: entry.role,
          stats: entry.stats,
          distanceRun: 0,
          stamina: 1,
          x: 0,
          z: 0,
          y: 0,
          vx: 0,
          vy: 0,
          vz: 0,
          facing: team === 0 ? 0 : Math.PI,
          onBench: i >= 18
        });
      });
    }
  }
  startMatch() {
    this.state.clock.quarter = 1;
    this.state.clock.secondsRemaining = this.state.settings.quarterSeconds;
    this.state.scores = [{ goals: 0, behinds: 0 }, { goals: 0, behinds: 0 }];
    this.beginQuarter();
    this.emit({ type: "centreBallUp", x: 0, z: 0 });
  }
  beginQuarter() {
    this.state.clock.running = false;
    this.state.clock.timeOn = 0;
    this.state.phase = "centreBallUp";
    this.phaseTimer = 1.6;
    this.state.restartX = 0;
    this.state.restartZ = 0;
    this.setupSixSixSix();
  }
  /** Place players in the 6-6-6 formation for a centre ball-up. */
  setupSixSixSix() {
    for (const team of [0, 1]) {
      const dir = team === 0 ? 1 : -1;
      const on = this.state.players.filter((p) => p.team === team && !p.onBench);
      const slots = [];
      for (let i = 0; i < 6; i++) {
        const ang = -0.9 + i / 5 * 1.8;
        slots.push({ x: dir * (FIELD.goalLineX - 32 + Math.cos(ang) * 12), z: Math.sin(ang) * 34 });
      }
      for (let i = 0; i < 6; i++) {
        const ang = -0.9 + i / 5 * 1.8;
        slots.push({ x: -dir * (FIELD.goalLineX - 32 + Math.cos(ang) * 12), z: Math.sin(ang) * 34 });
      }
      const mid = [
        { x: dir * 3, z: 0 },
        { x: dir * 12, z: -14 },
        { x: dir * 12, z: 14 },
        { x: dir * 24, z: -22 },
        { x: dir * 24, z: 22 },
        { x: dir * 20, z: 0 }
      ];
      slots.push(...mid);
      on.forEach((p, i) => {
        const s = slots[i % slots.length];
        p.x = s.x + (this.rng() - 0.5) * 2;
        p.z = s.z + (this.rng() - 0.5) * 2;
        p.vx = 0;
        p.vz = 0;
        p.y = 0;
      });
    }
  }
  // ----------------------------------------------------------------- clock
  step(dt) {
    const s = this.state;
    const phaseAtStart = s.phase;
    switch (s.phase) {
      case "centreBallUp":
      case "ballUp":
      case "throwIn":
        this.phaseTimer -= dt;
        if (this.phaseTimer <= 0) this.completeRestart();
        break;
      case "scoreCelebration":
        this.phaseTimer -= dt;
        if (this.phaseTimer <= 0) this.completeCelebration();
        break;
      case "quarterBreak":
        this.phaseTimer -= dt;
        if (this.phaseTimer <= 0) this.startNextQuarter();
        break;
      case "freeKick":
      case "kickIn":
        if (s.freeKick) {
          s.freeKick.shotClock -= dt;
          if (s.phase === "kickIn") this.kickInTimer += dt;
          if (s.freeKick.shotClock <= 0) this.shotClockExpired();
        }
        break;
      default:
        break;
    }
    const running = phaseAtStart === "live" || phaseAtStart === "freeKick" || phaseAtStart === "kickIn" || phaseAtStart === "ballUp" || phaseAtStart === "throwIn";
    s.clock.running = running || s.phase === "live";
    if (running) {
      s.clock.secondsRemaining -= dt;
      if (s.clock.secondsRemaining <= 0) {
        s.clock.secondsRemaining = 0;
        this.endQuarter();
      }
    } else if (phaseAtStart !== "quarterBreak" && phaseAtStart !== "preMatch" && phaseAtStart !== "matchEnd") {
      s.clock.timeOn += dt;
    }
    const b = s.ball;
    if (b.mode === "held" && b.holderId !== null) {
      if (s.clock.secondsRemaining >= 0 && this.possession.holderSince >= 0) {
        const held = this.elapsedHeld();
        if (held > 0.35) this.possession.priorOpportunity = true;
      }
    }
  }
  elapsedHeld() {
    return this.state.settings.quarterSeconds - this.state.clock.secondsRemaining - this.possession.holderSince;
  }
  // ------------------------------------------------------------ restarts
  completeRestart() {
    const s = this.state;
    const b = s.ball;
    b.mode = "loose";
    b.holderId = null;
    b.lastDisposal = "none";
    b.touched = false;
    b.bounced = false;
    b.kickDistance = 0;
    b.x = s.restartX;
    b.z = s.restartZ;
    b.y = 2.1;
    b.vx = (this.rng() - 0.5) * 1.5;
    b.vy = 1.2;
    b.vz = (this.rng() - 0.5) * 1.5;
    s.phase = "live";
    s.freeKick = null;
  }
  completeCelebration() {
    const s = this.state;
    if (s.phase === "matchEnd") return;
    if (!this.celebrationIsGoal) {
      this.startKickIn(this.celebrationDefendingTeam);
    } else {
      s.phase = "centreBallUp";
      this.phaseTimer = 1.4;
      s.restartX = 0;
      s.restartZ = 0;
      this.setupSixSixSix();
    }
  }
  startKickIn(defendingTeam) {
    const s = this.state;
    const gx = defendGoalX(defendingTeam);
    s.phase = "kickIn";
    this.kickInTimer = 0;
    const taker = this.nearestPlayer(defendingTeam, gx, 0, true);
    const spot = clampInside(gx + (defendingTeam === 0 ? 6 : -6), 0);
    if (taker) {
      taker.x = spot.x;
      taker.z = spot.z;
      this.giveBallTo(taker.id);
    }
    s.freeKick = makeFreeKick(defendingTeam, taker ? taker.id : -1, spot.x, spot.z, "advantage", {
      shotClock: FIELD.restartSeconds
    });
    this.emit({ type: "kickIn", team: defendingTeam, playerId: taker?.id, x: spot.x, z: spot.z });
  }
  startBallUp(x, z, throwIn = false) {
    const s = this.state;
    const spot = clampInside(x, z);
    s.restartX = spot.x;
    s.restartZ = spot.z;
    s.phase = throwIn ? "throwIn" : "ballUp";
    this.phaseTimer = throwIn ? 1.1 : 0.8;
    s.freeKick = null;
    const b = s.ball;
    b.mode = "dead";
    b.holderId = null;
    b.x = spot.x;
    b.z = spot.z;
    b.y = 2;
    this.emit({ type: throwIn ? "throwIn" : "ballUp", x: spot.x, z: spot.z });
  }
  /** Bring the ball back into play after a mark or free kick. */
  awardFreeKick(fk) {
    const s = this.state;
    s.freeKick = fk;
    s.phase = "freeKick";
    s.clock.running = true;
    const taker = s.players.find((p) => p.id === fk.takerId);
    if (taker) {
      taker.x = fk.x;
      taker.z = fk.z;
      this.giveBallTo(taker.id);
    } else if (s.players.length > 0) {
      const t = this.nearestPlayer(fk.team, fk.x, fk.z, true);
      if (t) {
        fk.takerId = t.id;
        t.x = fk.x;
        t.z = fk.z;
        this.giveBallTo(t.id);
      }
    }
    fk.isSetShot = isSetShot(fk);
    if (fk.isSetShot) {
      s.setShotDeadline = s.clock.secondsRemaining - FIELD.restartSeconds;
    }
    this.emit({
      type: "freeKick",
      team: fk.team,
      playerId: fk.takerId,
      x: fk.x,
      z: fk.z,
      text: fk.reason
    });
    if (fk.fiftyMetres) this.emit({ type: "fiftyMetres", team: fk.team, playerId: fk.takerId });
    if (fk.isMark) this.emit({ type: "mark", team: fk.team, playerId: fk.takerId });
  }
  shotClockExpired() {
    const s = this.state;
    const fk = s.freeKick;
    if (!fk) return;
    if (s.phase === "kickIn") {
      const other = fk.team === 0 ? 1 : 0;
      const spot = clampInside(fk.x, fk.z);
      this.awardFreeKick(
        makeFreeKick(other, -1, spot.x, spot.z, "kickInNotCleared")
      );
      return;
    }
    this.startBallUp(fk.x, fk.z);
    this.emit({ type: "hold", text: "Time!" });
  }
  // ------------------------------------------------------------- possession
  giveBallTo(playerId) {
    const s = this.state;
    const p = s.players.find((x) => x.id === playerId);
    if (!p) return;
    const b = s.ball;
    b.mode = "held";
    b.holderId = playerId;
    b.x = p.x;
    b.z = p.z;
    b.y = 1.1;
    b.vx = 0;
    b.vy = 0;
    b.vz = 0;
    b.kickDistance = 0;
    this.possession = {
      holderSince: this.state.settings.quarterSeconds - this.state.clock.secondsRemaining,
      priorOpportunity: false,
      metresSinceBounce: 0,
      shrugOrFend: false
    };
  }
  /** Player gained possession in open play (pickup or short handball receive). */
  onPossessionGained(playerId) {
    const wasLive = this.state.phase === "live";
    this.giveBallTo(playerId);
    if (!wasLive && (this.state.phase === "freeKick" || this.state.phase === "kickIn")) {
      return;
    }
  }
  onBounce(playerId) {
    if (this.state.ball.holderId === playerId) {
      this.possession.metresSinceBounce = 0;
    }
    this.state.ball.bounced = true;
    this.emit({ type: "stat", playerId, text: "bounce" });
  }
  onTouchDown(playerId) {
    if (this.state.ball.holderId === playerId) {
      this.possession.metresSinceBounce = 0;
    }
  }
  onShrugOrFend(playerId) {
    if (this.state.ball.holderId === playerId) {
      this.possession.shrugOrFend = true;
      this.possession.priorOpportunity = true;
    }
  }
  /** Accumulate run-with-ball distance; enforces the 15 m bounce law. */
  onRunMetres(playerId, metres) {
    const b = this.state.ball;
    if (b.holderId !== playerId) return;
    this.possession.metresSinceBounce += metres;
    const call = decideRunTooFar(this.possession.metresSinceBounce, false);
    if (call.kind === "freeKick") {
      const p = this.state.players.find((x) => x.id === playerId);
      if (p) {
        const other = p.team === 0 ? 1 : 0;
        this.awardFreeKick(makeFreeKick(other, -1, p.x, p.z, "runningTooFar"));
        this.emit({ type: "freeKick", team: other, text: "runningTooFar", x: p.x, z: p.z });
      }
    }
  }
  onKick(playerId, opts = {}) {
    const s = this.state;
    const b = s.ball;
    const p = s.players.find((x) => x.id === playerId);
    if (!p) return;
    b.mode = "loose";
    b.holderId = null;
    b.lastDisposal = opts.handball ? "handball" : "kick";
    b.kickedById = playerId;
    b.handballedById = opts.handball ? playerId : null;
    b.kickedFromX = p.x;
    b.kickedFromZ = p.z;
    b.kickDistance = 0;
    b.touched = false;
    b.bounced = false;
    b.kickedAt = s.settings.quarterSeconds - s.clock.secondsRemaining;
    if (s.phase === "freeKick" || s.phase === "kickIn") {
      s.phase = "live";
      s.freeKick = null;
      this.emit({ type: "playOn", playerId });
    }
    this.possession.metresSinceBounce = 0;
    this.emit({ type: "stat", playerId, text: opts.handball ? "handball" : "kick" });
  }
  /** Ball caught in flight — checks the mark. */
  onBallCaught(playerId) {
    const s = this.state;
    const p = s.players.find((x) => x.id === playerId);
    if (!p) return;
    const snapshot = { ...s.ball, mode: "held", holderId: playerId };
    const decision = decideMark(snapshot, p);
    this.giveBallTo(playerId);
    if (decision.kind === "mark") {
      this.emit({ type: "mark", team: p.team, playerId, x: p.x, z: p.z });
      this.awardFreeKick(
        makeFreeKick(p.team, playerId, p.x, p.z, "mark", { isMark: true })
      );
    }
  }
  onTackle(tacklerId, carrierId, ctx) {
    const s = this.state;
    const tackler = s.players.find((p) => p.id === tacklerId);
    const carrier = s.players.find((p) => p.id === carrierId);
    if (!tackler || !carrier) return;
    const prior = this.possession.priorOpportunity || this.possession.shrugOrFend;
    const decision = decideTackle(tackler, carrier, {
      ...ctx,
      priorOpportunity: prior || ctx.priorOpportunity
    });
    switch (decision.kind) {
      case "holdingTheBall":
      case "incorrectDisposal":
        this.emit({ type: "tackle", playerId: tacklerId, x: carrier.x, z: carrier.z });
        this.awardFreeKick(
          makeFreeKick(
            tackler.team,
            tacklerId,
            carrier.x,
            carrier.z,
            decision.kind === "holdingTheBall" ? "holdingTheBall" : "throwing"
          )
        );
        break;
      case "highTackle":
      case "pushInTheBack":
        this.emit({ type: "tackle", playerId: tacklerId });
        this.awardFreeKick(
          makeFreeKick(
            carrier.team,
            carrierId,
            carrier.x,
            carrier.z,
            decision.kind === "highTackle" ? "highTackle" : "pushInTheBack"
          )
        );
        break;
      case "legalTacklePlayOn": {
        this.emit({ type: "tackle", playerId: tacklerId });
        this.giveBallTo(tacklerId);
        break;
      }
      case "noPriorBallUp":
        this.emit({ type: "tackle", playerId: tacklerId });
        this.startBallUp(carrier.x, carrier.z);
        break;
    }
  }
  /** An opponent infringed inside the protected area or interfered → 50 m. */
  onProtectedAreaBreach(playerId) {
    const s = this.state;
    const fk = s.freeKick;
    if (!fk) return;
    const p = s.players.find((x) => x.id === playerId);
    if (!p || p.team === fk.team) return;
    const upgraded = applyFiftyMetrePenalty(fk);
    upgraded.reason = "protectedArea";
    this.awardFreeKick(upgraded);
    this.emit({ type: "fiftyMetres", team: fk.team, playerId: fk.takerId });
  }
  onInterferenceAfterMark(playerId) {
    this.onProtectedAreaBreach(playerId);
  }
  // ------------------------------------------------------------ ball flight
  /** Called by the sim each frame the ball is loose: tracks flight distance. */
  onBallFlight(dt) {
    const b = this.state.ball;
    if (b.mode === "loose" && b.lastDisposal !== "none") {
      b.kickDistance += Math.hypot(b.vx, b.vy, b.vz) * dt;
    }
  }
  onBallTouched(playerId) {
    this.state.ball.touched = true;
    this.emit({ type: "touch", playerId });
  }
  onBallBounced() {
    this.state.ball.bounced = true;
    this.state.ball.kickDistance = 0;
    this.state.ball.touched = this.state.ball.touched || false;
  }
  /**
   * The whole ball crossed the boundary line (not the goal line).
   * `prev` is the previous in-bounds position for the crossing point.
   */
  onBoundaryCrossed(prevX, prevZ, crossed, smotheredOrDeflected, deliberate) {
    const s = this.state;
    const b = s.ball;
    const crossing = boundaryCrossing(prevX, prevZ, crossed.x, crossed.z);
    const holder = b.holderId !== null ? s.players.find((p) => p.id === b.holderId) : null;
    const lastTouchTeam = holder?.team ?? (b.kickedById !== null ? s.players.find((p) => p.id === b.kickedById)?.team ?? null : null);
    const decision = decideOutOfBounds(
      b,
      crossing.x,
      crossing.z,
      lastTouchTeam,
      smotheredOrDeflected,
      deliberate
    );
    b.mode = "dead";
    b.holderId = null;
    switch (decision.kind) {
      case "outOnTheFull":
      case "lastDisposal":
      case "deliberate": {
        this.emit({
          type: decision.kind === "outOnTheFull" ? "outOnTheFull" : "lastDisposal",
          team: decision.toTeam,
          x: decision.x,
          z: decision.z,
          text: decision.kind
        });
        const taker = this.nearestPlayer(decision.toTeam, decision.x, decision.z, true);
        this.awardFreeKick(
          makeFreeKick(
            decision.toTeam,
            taker ? taker.id : -1,
            decision.x,
            decision.z,
            decision.kind === "outOnTheFull" ? "outOnTheFull" : decision.kind === "lastDisposal" ? "lastDisposalOOB" : "deliberateOOB"
          )
        );
        break;
      }
      case "throwIn":
        this.startBallUp(decision.x, decision.z, true);
        break;
    }
    void isOutOfBounds;
  }
  /**
   * The ball crossed the goal line (between the behind posts) or hit a post.
   * `endX` sign: +1 = east goal line, -1 = west.
   */
  onGoalLineCrossed(crossX, crossZ, opts = {}) {
    const s = this.state;
    const b = s.ball;
    const at = scoreAtCrossing(crossX, crossZ);
    if (!at) return;
    const scoringTeam = crossX > 0 ? 0 : 1;
    const otherTeam = scoringTeam === 0 ? 1 : 0;
    b.mode = "dead";
    b.holderId = null;
    if (opts.postHit === "behindPost") {
      if (!b.bounced) {
        this.emit({ type: "outOnTheFull", team: otherTeam, x: crossX, z: crossZ });
        const taker = this.nearestPlayer(otherTeam, crossX, crossZ, true);
        this.awardFreeKick(
          makeFreeKick(otherTeam, taker ? taker.id : -1, crossX, crossZ, "outOnTheFull")
        );
      } else {
        this.startBallUp(crossX, crossZ, true);
      }
      return;
    }
    if (opts.postHit === "goalPost") {
      applyScore(s.scores, { kind: "goalPost", behindTeam: scoringTeam });
      this.emit({ type: "behind", team: scoringTeam, points: 1, x: crossX, z: crossZ });
      this.celebrate(false, otherTeam);
      return;
    }
    const isGoal = at.kind === "goal" && !b.touched && b.lastDisposal === "kick";
    if (isGoal) {
      applyScore(s.scores, { kind: "goal", team: scoringTeam, points: 6 });
      this.emit({ type: "goal", team: scoringTeam, points: 6, x: crossX, z: crossZ });
      this.celebrate(true, otherTeam);
      return;
    }
    applyScore(s.scores, { kind: "behind", team: scoringTeam, points: 1 });
    this.emit({ type: "behind", team: scoringTeam, points: 1, x: crossX, z: crossZ });
    if (opts.deliberateRush) {
      const gx = attackGoalX(scoringTeam);
      const spot = clampInside(gx - Math.sign(gx) * 15, 0);
      this.emit({ type: "freeKick", team: scoringTeam, text: "deliberateRushedBehind" });
      const taker = this.nearestPlayer(scoringTeam, spot.x, spot.z, true);
      this.awardFreeKick(
        makeFreeKick(scoringTeam, taker ? taker.id : -1, spot.x, spot.z, "deliberateRushedBehind")
      );
      return;
    }
    this.celebrate(false, otherTeam);
  }
  celebrate(wasGoal, defendingTeam) {
    const s = this.state;
    s.phase = "scoreCelebration";
    this.phaseTimer = 3.2;
    this.celebrationIsGoal = wasGoal;
    this.celebrationDefendingTeam = defendingTeam;
    s.clock.running = false;
    this.emit({ type: "siren", text: "score" });
  }
  // ------------------------------------------------------------- quarters
  endQuarter() {
    const s = this.state;
    s.phase = "quarterBreak";
    s.clock.running = false;
    this.phaseTimer = 6;
    s.ball.mode = "dead";
    s.ball.holderId = null;
    this.emit({ type: "quarterEnd", text: `Q${s.clock.quarter}` });
    if (s.clock.quarter >= s.settings.quarters) {
      this.emit({ type: "siren", text: "final" });
    }
  }
  startNextQuarter() {
    const s = this.state;
    if (s.clock.quarter >= s.settings.quarters) {
      s.phase = "matchEnd";
      const m = totalPoints(s.scores[0]) - totalPoints(s.scores[1]);
      s.winner = m === 0 ? null : m > 0 ? 0 : 1;
      this.emit({ type: "matchEnd", text: s.winner === null ? "draw" : `team${s.winner}` });
      return;
    }
    s.clock.quarter += 1;
    s.clock.secondsRemaining = s.settings.quarterSeconds;
    s.clock.timeOn = 0;
    this.beginQuarter();
    this.emit({ type: "centreBallUp", x: 0, z: 0 });
  }
  // -------------------------------------------------------------- utilities
  nearestPlayer(team, x, z, excludeBench = true) {
    let best = null;
    let bestD = Infinity;
    for (const p of this.state.players) {
      if (p.team !== team) continue;
      if (excludeBench && p.onBench) continue;
      const d = (p.x - x) ** 2 + (p.z - z) ** 2;
      if (d < bestD) {
        bestD = d;
        best = p;
      }
    }
    return best;
  }
  nearestToBall() {
    const b = this.state.ball;
    return this.nearestPlayer(0, b.x, b.z) ?? this.nearestPlayer(1, b.x, b.z);
  }
  callPlayOn() {
    const s = this.state;
    if (s.phase === "freeKick" || s.phase === "kickIn") {
      s.phase = "live";
      s.freeKick = null;
      this.emit({ type: "playOn" });
    }
  }
  drainEvents() {
    const ev = this.state.events;
    this.state.events = [];
    return ev;
  }
  emit(e) {
    this.state.events.push(e);
  }
  /** Human/AI helper: where should a kick for goal be aimed? */
  targetGoalPoint(team) {
    return { x: attackGoalX(team), z: 0 };
  }
};

// src/sim/ball.ts
var BALL_RADIUS = 0.15;
var GRAVITY = 9.81;
var AIR_DRAG = 0.06;
var BOUNCE_RESTITUTION = 0.52;
var GROUND_FRICTION = 0.8;
var ROLL_FRICTION = 1.4;
function stepBall(ball, dt, rng = Math.random) {
  const prevX = ball.x;
  const prevY = ball.y;
  const prevZ = ball.z;
  const res = {
    prevX,
    prevY,
    prevZ,
    bounced: false,
    crossedBoundary: false,
    crossedGoalLine: false,
    goalLineSide: 1,
    postHit: null
  };
  if (ball.mode === "held" || ball.mode === "heldUmpire" || ball.mode === "dead") {
    return res;
  }
  const speed = Math.hypot(ball.vx, ball.vy, ball.vz);
  const drag = AIR_DRAG * speed;
  if (speed > 1e-3) {
    ball.vx -= ball.vx / speed * drag * dt;
    ball.vy -= ball.vy / speed * drag * dt;
    ball.vz -= ball.vz / speed * drag * dt;
  }
  ball.vz += ball.spin * dt * 1.4;
  ball.spin *= 1 - 0.35 * dt;
  ball.vy -= GRAVITY * dt;
  ball.x += ball.vx * dt;
  ball.y += ball.vy * dt;
  ball.z += ball.vz * dt;
  if (ball.y <= BALL_RADIUS && ball.vy < 0) {
    ball.y = BALL_RADIUS;
    ball.vy = -ball.vy * BOUNCE_RESTITUTION * (0.85 + rng() * 0.3);
    ball.vx *= GROUND_FRICTION;
    ball.vz *= GROUND_FRICTION;
    ball.spin *= 0.6;
    if (Math.abs(ball.vy) < 0.6) ball.vy = 0;
    res.bounced = true;
  } else if (ball.y <= BALL_RADIUS + 0.02 && Math.abs(ball.vy) < 0.3) {
    const f = Math.max(0, 1 - ROLL_FRICTION * dt);
    ball.vx *= f;
    ball.vz *= f;
    ball.y = BALL_RADIUS;
    ball.vy = 0;
  }
  const nearGoalLine = Math.abs(Math.abs(ball.x) - FIELD.goalLineX) < 0.35;
  if (nearGoalLine && ball.y < 10) {
    const az = Math.abs(ball.z);
    const dGoal = Math.abs(az - FIELD.goalPostHalf);
    const dBehind = Math.abs(az - FIELD.behindPostHalf);
    if (dGoal < 0.45 && ball.y < 9.6) {
      res.postHit = "goalPost";
      ball.vx = -ball.vx * 0.4;
      ball.vz += (ball.z > 0 ? 1 : -1) * 2.5;
    } else if (dBehind < 0.45 && ball.y < 6) {
      res.postHit = "behindPost";
      ball.vx = -ball.vx * 0.4;
      ball.vz += (ball.z > 0 ? 1 : -1) * 2.5;
    }
  }
  const goalLineX = FIELD.goalLineX;
  if (prevX < goalLineX && ball.x >= goalLineX && Math.abs(ball.z) <= FIELD.behindPostHalf + 0.2) {
    res.crossedGoalLine = true;
    res.goalLineSide = 1;
  } else if (prevX > -goalLineX && ball.x <= -goalLineX && Math.abs(ball.z) <= FIELD.behindPostHalf + 0.2) {
    res.crossedGoalLine = true;
    res.goalLineSide = -1;
  }
  if (!res.crossedGoalLine && isOutOfBounds(ball.x, ball.z, BALL_RADIUS)) {
    res.crossedBoundary = true;
  }
  return res;
}
function launchKick(ball, fromX, fromY, fromZ, dirX, dirZ, power, accuracy, rng) {
  const dist = 8 + power * 52;
  const noise = (1 - accuracy) * 0.16;
  const ang = Math.atan2(dirZ, dirX) + (rng() - 0.5) * noise * 2;
  const loft = 0.22 + power * 0.32 + (rng() - 0.5) * noise;
  const speed = Math.sqrt(dist * GRAVITY / Math.max(0.35, Math.sin(2 * loft))) * 1.15;
  ball.mode = "loose";
  ball.holderId = null;
  ball.x = fromX;
  ball.y = fromY;
  ball.z = fromZ;
  ball.vx = Math.cos(ang) * speed * Math.cos(loft);
  ball.vz = Math.sin(ang) * speed * Math.cos(loft);
  ball.vy = speed * Math.sin(loft);
  ball.spin = (rng() - 0.5) * 1.2;
}
function launchHandball(ball, fromX, fromY, fromZ, dirX, dirZ, power, rng) {
  const dist = 4 + power * 16;
  const speed = 7 + power * 15;
  const ang = Math.atan2(dirZ, dirX) + (rng() - 0.5) * 0.12;
  ball.mode = "loose";
  ball.holderId = null;
  ball.x = fromX;
  ball.y = fromY;
  ball.z = fromZ;
  ball.vx = Math.cos(ang) * speed * 0.92;
  ball.vz = Math.sin(ang) * speed * 0.92;
  ball.vy = 1.8 + power * 1.6;
  ball.spin = 0;
  void dist;
}

// src/sim/ai.ts
function emptyIntent() {
  return {
    moveX: 0,
    moveZ: 0,
    sprint: false,
    wantKick: false,
    wantHandball: false,
    wantTackle: false,
    wantBounce: false,
    aimX: 1,
    aimZ: 0,
    power: 0.6
  };
}
var DIFF = {
  rookie: { reaction: 0.55, accuracy: 0.72, pressure: 0.5, speed: 0.93 },
  club: { reaction: 0.78, accuracy: 0.84, pressure: 0.8, speed: 0.98 },
  afl: { reaction: 0.95, accuracy: 0.92, pressure: 1, speed: 1 }
};
var ROLE_SHAPE = {
  fullback: { fx: -0.38, fz: 0 },
  keyDefender: { fx: -0.3, fz: 0.18 },
  halfBack: { fx: -0.16, fz: 0.3 },
  midfielder: { fx: 0, fz: 0.22 },
  ruck: { fx: 0.02, fz: 0 },
  halfForward: { fx: 0.16, fz: 0.3 },
  keyForward: { fx: 0.3, fz: 0.18 },
  fullForward: { fx: 0.38, fz: 0 }
};
function homePosition(p, ballX, ballZ, phase) {
  const dir = p.team === 0 ? 1 : -1;
  const shape = ROLE_SHAPE[p.role] ?? ROLE_SHAPE.midfielder;
  const anchorX = ballX * 0.55;
  const anchorZ = ballZ * 0.45;
  let x = anchorX + dir * shape.fx * 72;
  let z = anchorZ + shape.fz * 52 * (p.id % 2 === 0 ? 1 : -1);
  if (phase === "centreBallUp") {
    const gx = attackGoalX(p.team);
    const dg = defendGoalX(p.team);
    if (shape.fx > 0.1) {
      x = gx - dir * (28 + shape.fx * 20);
    } else if (shape.fx < -0.1) {
      x = dg + dir * (28 + -shape.fx * 20);
    } else {
      x = dir * 14;
    }
    z = shape.fz * 60 * (p.number % 2 === 0 ? 1 : -1) + p.number % 5 * 4 - 8;
  }
  return {
    x: Math.max(-FIELD.boundaryA + 6, Math.min(FIELD.boundaryA - 6, x)),
    z: Math.max(-FIELD.boundaryB + 6, Math.min(FIELD.boundaryB - 6, z))
  };
}
function aiIntentFor(p, ctx) {
  const intent = emptyIntent();
  const s = ctx.state;
  const b = s.ball;
  const diff = DIFF[ctx.difficulty];
  const dir = p.team === 0 ? 1 : -1;
  if (p.onBench) return intent;
  const toBallX = b.x - p.x;
  const toBallZ = b.z - p.z;
  const distBall = Math.hypot(toBallX, toBallZ);
  if (ctx.carrierId === p.id && b.mode === "held") {
    const goalX = attackGoalX(p.team);
    const distGoal = Math.hypot(goalX - p.x, 0 - p.z);
    const pressured = isPressured(p, ctx);
    if (s.phase === "kickIn") {
      intent.wantKick = true;
      intent.power = 0.75;
      const target = bestKickTarget(p, ctx) ?? { x: dir * 30, z: (p.number % 2 ? 1 : -1) * 40 };
      aim(intent, p, target.x, target.z);
      return intent;
    }
    if (insideAttackArc(p.x, p.z, p.team) && distGoal < 52) {
      intent.wantKick = true;
      intent.power = Math.min(1, 0.55 + distGoal / 70);
      const spread = (1 - diff.accuracy) * (distGoal / 60);
      const z = (ctx.rng() - 0.5) * spread * 10;
      aim(intent, p, goalX, z);
      return intent;
    }
    if (pressured && ctx.rng() < 0.035 * diff.reaction * 60 * 0.02) {
      const mate = bestHandballTarget(p, ctx);
      if (mate) {
        intent.wantHandball = true;
        aim(intent, p, mate.x, mate.z);
        return intent;
      }
    }
    if (ctx.liveTime > 1.2 && ctx.rng() < 0.028 + 0.02 * diff.reaction) {
      const target = bestKickTarget(p, ctx);
      intent.wantKick = true;
      intent.power = 0.55 + ctx.rng() * 0.35;
      if (target) aim(intent, p, target.x, target.z);
      else aim(intent, p, p.x + dir * 40, p.z * 0.4);
      return intent;
    }
    const gap = bestRunGap(p, ctx);
    intent.moveX = gap.x;
    intent.moveZ = gap.z;
    intent.sprint = true;
    return intent;
  }
  const loose = b.mode === "loose";
  const mayChase = teammatesCloserToBall(p, ctx) < 3;
  const chaseThis = mayChase && (loose && distBall < 11 || ctx.possessingTeam !== null && ctx.possessingTeam !== p.team && distBall < 8 || ctx.carrierId !== null && isNearestChaser(p, ctx));
  if (chaseThis) {
    const lead = 0.28 * diff.reaction;
    intent.moveX = normalize(toBallX + b.vx * lead);
    intent.moveZ = normalize(toBallZ + b.vz * lead);
    intent.sprint = distBall > 6;
    if (distBall < 1.6 && ctx.possessingTeam !== null && ctx.possessingTeam !== p.team) {
      intent.wantTackle = true;
    }
    return intent;
  }
  const home = homePosition(p, b.x, b.z, s.phase);
  const hx = home.x - p.x;
  const hz = home.z - p.z;
  const d = Math.hypot(hx, hz);
  if (d > 2.5) {
    intent.moveX = normalize(hx);
    intent.moveZ = normalize(hz);
    intent.sprint = d > 18;
  }
  if (ctx.possessingTeam === p.team && (p.role === "keyForward" || p.role === "fullForward" || p.role === "halfForward")) {
    const goalX = attackGoalX(p.team);
    intent.moveX = normalize((goalX - p.x) * 0.5 + hx);
    intent.moveZ = normalize(-p.z * 0.6 + hz * 0.4);
    intent.sprint = true;
  }
  if (ctx.possessingTeam !== null && ctx.possessingTeam !== p.team && (p.role === "fullback" || p.role === "keyDefender")) {
    const ownGoal = defendGoalX(p.team);
    const dangerX = ownGoal + dir * 18;
    intent.moveX = normalize(dangerX - p.x);
    intent.moveZ = normalize(-p.z * 0.5);
  }
  return intent;
}
function teammatesCloserToBall(p, ctx) {
  const b = ctx.state.ball;
  const d = (b.x - p.x) ** 2 + (b.z - p.z) ** 2;
  let n = 0;
  for (const q of ctx.state.players) {
    if (q.team !== p.team || q.id === p.id || q.onBench) continue;
    if ((b.x - q.x) ** 2 + (b.z - q.z) ** 2 < d) n++;
  }
  return n;
}
function isPressured(p, ctx) {
  for (const q of ctx.state.players) {
    if (q.team === p.team || q.onBench) continue;
    if (Math.hypot(q.x - p.x, q.z - p.z) < 3.2) return true;
  }
  return false;
}
function isNearestChaser(p, ctx) {
  const b = ctx.state.ball;
  let best = Infinity;
  let mine = Infinity;
  for (const q of ctx.state.players) {
    if (q.onBench) continue;
    const d = (q.x - b.x) ** 2 + (q.z - b.z) ** 2;
    if (d < best) best = d;
    if (q.team === p.team && d < mine) mine = d;
  }
  return mine <= best * 1.05;
}
function bestKickTarget(p, ctx) {
  const dir = p.team === 0 ? 1 : -1;
  const goalX = attackGoalX(p.team);
  let best = null;
  for (const q of ctx.state.players) {
    if (q.team !== p.team || q.id === p.id || q.onBench) continue;
    const dx = q.x - p.x;
    if (dx * dir < -6) continue;
    const dist = Math.hypot(dx, q.z - p.z);
    if (dist < 8 || dist > 62) continue;
    const dGoal = Math.hypot(goalX - q.x, q.z * 0.7);
    let pressure = 0;
    for (const o of ctx.state.players) {
      if (o.team === p.team || o.onBench) continue;
      pressure += Math.max(0, 8 - Math.hypot(o.x - q.x, o.z - q.z));
    }
    const score = -dGoal * 0.12 - pressure * 0.55 + ctx.rng() * 2.2;
    if (!best || score > best.score) {
      best = { x: q.x + dir * 3, z: q.z, player: q, score };
    }
  }
  return best ? { x: best.x, z: best.z, player: best.player } : null;
}
function bestHandballTarget(p, ctx) {
  let best = null;
  for (const q of ctx.state.players) {
    if (q.team !== p.team || q.id === p.id || q.onBench) continue;
    const d = Math.hypot(q.x - p.x, q.z - p.z);
    if (d > 22) continue;
    let pressure = 0;
    for (const o of ctx.state.players) {
      if (o.team === p.team || o.onBench) continue;
      pressure += Math.max(0, 5 - Math.hypot(o.x - q.x, o.z - q.z));
    }
    const value = d - pressure * 3;
    if (!best || value < best.d) best = { x: q.x, z: q.z, d: value };
  }
  return best ? { x: best.x, z: best.z } : null;
}
function bestRunGap(p, ctx) {
  const dir = p.team === 0 ? 1 : -1;
  let bestX = dir;
  let bestZ = -p.z * 0.02;
  let bestScore = -Infinity;
  for (let a = -1.1; a <= 1.1; a += 0.28) {
    const dx = Math.cos(a) * dir;
    const dz = Math.sin(a);
    let pressure = 0;
    for (const o of ctx.state.players) {
      if (o.team === p.team || o.onBench) continue;
      const px = p.x + dx * 6 - o.x;
      const pz = p.z + dz * 6 - o.z;
      pressure += Math.max(0, 7 - Math.hypot(px, pz));
    }
    const forward = dx * dir * 3;
    const score = forward - pressure * 1.35 + ctx.rng() * 0.6;
    if (score > bestScore) {
      bestScore = score;
      bestX = dx;
      bestZ = dz;
    }
  }
  return { x: bestX, z: bestZ };
}
function normalize(v) {
  return Math.max(-1, Math.min(1, v));
}
function aim(intent, p, x, z) {
  const dx = x - p.x;
  const dz = z - p.z;
  const d = Math.hypot(dx, dz) || 1;
  intent.aimX = dx / d;
  intent.aimZ = dz / d;
}

// src/sim/match.ts
function emptyHumanIntent() {
  return {
    moveX: 0,
    moveZ: 0,
    sprint: false,
    kickHeld: false,
    kickReleased: false,
    handball: false,
    tackle: false,
    switchPlayer: false,
    bounce: false,
    aimZ: 0
  };
}
var CATCH_RADIUS = 1.45;
var TACKLE_RADIUS = 1.55;
var SEPARATION_RADIUS = 0.72;
var MatchSim = class {
  engine;
  difficulty;
  humanTeam;
  controlledId;
  kickCharge = 0;
  rng;
  liveTime = 0;
  runSinceBounce = 0;
  eventsOut = [];
  /** Player who last disposed of the ball; can't regather it briefly (smother/protection). */
  kickGraceId = -1;
  kickGraceT = 0;
  constructor(settings2, difficulty = "afl", humanTeam = 0) {
    this.engine = new RulesEngine(settings2);
    this.difficulty = difficulty;
    this.humanTeam = humanTeam;
    this.rng = mulberry32(settings2.seed ^ 24415);
    this.controlledId = -1;
  }
  start() {
    this.engine.buildTeams();
    this.engine.startMatch();
    this.pickControlled(true);
  }
  get state() {
    return this.engine.state;
  }
  // ------------------------------------------------------------- control
  pickControlled(force = false) {
    const s = this.engine.state;
    const b = s.ball;
    const candidates = s.players.filter((p) => p.team === this.humanTeam && !p.onBench);
    if (candidates.length === 0) return;
    if (s.freeKick && s.freeKick.team === this.humanTeam && s.freeKick.takerId >= 0) {
      const taker = candidates.find((p) => p.id === s.freeKick.takerId);
      if (taker) {
        this.controlledId = taker.id;
        return;
      }
    }
    const current = candidates.find((p) => p.id === this.controlledId);
    const dist = (p) => (p.x - b.x) ** 2 + (p.z - b.z) ** 2;
    if (!force && current) {
      if (b.mode === "loose") {
        const nearest2 = candidates.reduce((a, c) => dist(c) < dist(a) ? c : a);
        if (dist(nearest2) < dist(current) * 0.35) this.controlledId = nearest2.id;
      }
      return;
    }
    const nearest = candidates.reduce((a, c) => dist(c) < dist(a) ? c : a);
    this.controlledId = nearest.id;
  }
  switchPlayer() {
    const s = this.engine.state;
    const b = s.ball;
    const candidates = s.players.filter((p) => p.team === this.humanTeam && !p.onBench && p.id !== this.controlledId).sort(
      (a, c) => (a.x - b.x) ** 2 + (a.z - b.z) ** 2 - ((c.x - b.x) ** 2 + (c.z - b.z) ** 2)
    );
    if (candidates.length > 0) this.controlledId = candidates[0].id;
  }
  // -------------------------------------------------------------- update
  update(dt, human) {
    dt = Math.min(dt, 1 / 20);
    const s = this.engine.state;
    const b = s.ball;
    this.eventsOut = [];
    if (this.kickGraceT > 0) this.kickGraceT -= dt;
    const wasPhase = s.phase;
    this.engine.step(dt);
    if (s.phase !== wasPhase) {
      this.liveTime = 0;
      this.pickControlled();
    } else {
      this.liveTime += dt;
    }
    if (s.phase === "matchEnd") {
      this.eventsOut = this.engine.drainEvents();
      return this.eventsOut;
    }
    if (human.switchPlayer) this.switchPlayer();
    const carrier = b.mode === "held" && b.holderId !== null ? s.players.find((p) => p.id === b.holderId) ?? null : null;
    const ctx = {
      state: s,
      difficulty: this.difficulty,
      possessingTeam: carrier ? carrier.team : null,
      carrierId: carrier ? carrier.id : null,
      liveTime: this.liveTime,
      rng: this.rng
    };
    for (const p of s.players) {
      if (p.onBench) continue;
      const intent = p.id === this.controlledId ? humanToIntents(human, this.kickCharge) : aiIntentFor(p, ctx);
      this.movePlayer(p, intent, dt);
      if (p.id !== this.controlledId) {
        this.tryAiActions(p, intent, ctx);
      }
    }
    this.separatePlayers();
    if (b.mode === "held" && carrier) {
      const fwd = carrier.facing;
      b.x = carrier.x + Math.cos(fwd) * 0.55;
      b.z = carrier.z + Math.sin(fwd) * 0.55;
      b.y = 1.05;
      b.vx = carrier.vx;
      b.vz = carrier.vz;
      b.vy = 0;
      const moved = Math.hypot(carrier.vx, carrier.vz) * dt;
      this.runSinceBounce += moved;
      if (this.runSinceBounce > 0.01) this.engine.onRunMetres(carrier.id, moved);
      if (this.runSinceBounce > 11.2 || human.bounce && carrier.id === this.controlledId) {
        this.runSinceBounce = 0;
        this.engine.onBounce(carrier.id);
        b.y = 0.3;
      }
    } else if (b.mode === "loose") {
      const before = { x: b.x, z: b.z };
      const res = stepBall(b, dt, this.rng);
      this.engine.onBallFlight(dt);
      if (res.bounced) this.engine.onBallBounced();
      if (res.postHit) {
        const side = b.x > 0 ? 1 : -1;
        this.engine.onGoalLineCrossed(side * FIELD.goalLineX, b.z, {
          postHit: res.postHit
        });
      } else if (res.crossedGoalLine) {
        this.handleGoalLine(res.goalLineSide, before);
      } else if (res.crossedBoundary) {
        this.handleBoundary(before, b);
      } else {
        this.tryPickupOrCatch();
      }
    }
    if (b.mode === "held" && carrier) {
      this.tryTackles(carrier);
    }
    if (carrier && carrier.id === this.controlledId) {
      this.humanActions(carrier, human);
    }
    if (human.kickHeld) {
      this.kickCharge = Math.min(1, this.kickCharge + dt * 1.35);
    }
    const drained = this.engine.drainEvents();
    this.eventsOut.push(...drained);
    return this.eventsOut;
  }
  // ------------------------------------------------------------ movement
  movePlayer(p, intent, dt) {
    const stats = p.stats;
    const fatigue = 0.82 + 0.18 * p.stamina;
    const sprint = "sprint" in intent ? intent.sprint : false;
    const maxSpeed = (6.2 + stats.speed * 2.4) * fatigue * (sprint ? 1.14 : 1) * this.speedScale();
    let mx = intent.moveX;
    let mz = intent.moveZ;
    const mag = Math.hypot(mx, mz);
    if (mag > 1) {
      mx /= mag;
      mz /= mag;
    }
    const tvx = mx * maxSpeed;
    const tvz = mz * maxSpeed;
    const accel = mag > 0.05 ? 13 : 11;
    p.vx += (tvx - p.vx) * Math.min(1, accel * dt);
    p.vz += (tvz - p.vz) * Math.min(1, accel * dt);
    p.x += p.vx * dt;
    p.z += p.vz * dt;
    if (isOutOfBounds(p.x, p.z, 0.35)) {
      const spot = clampInside(p.x, p.z, 2.5);
      p.x = spot.x;
      p.z = spot.z;
      p.vx *= 0.4;
      p.vz *= 0.4;
    }
    const speed = Math.hypot(p.vx, p.vz);
    if (speed > 0.6) {
      const target = Math.atan2(p.vz, p.vx);
      let d = target - p.facing;
      while (d > Math.PI) d -= Math.PI * 2;
      while (d < -Math.PI) d += Math.PI * 2;
      p.facing += d * Math.min(1, 9 * dt);
    }
    p.distanceRun += speed * dt;
    p.stamina = Math.max(0.35, p.stamina - speed * dt * 22e-4);
    p.y = 0;
  }
  speedScale() {
    return this.difficulty === "rookie" ? 0.94 : this.difficulty === "club" ? 0.99 : 1;
  }
  separatePlayers() {
    const ps = this.engine.state.players.filter((p) => !p.onBench);
    for (let i = 0; i < ps.length; i++) {
      for (let j = i + 1; j < ps.length; j++) {
        const a = ps[i];
        const c = ps[j];
        const dx = c.x - a.x;
        const dz = c.z - a.z;
        const d = Math.hypot(dx, dz);
        if (d > 1e-3 && d < SEPARATION_RADIUS * 2) {
          const push = (SEPARATION_RADIUS * 2 - d) * 0.32;
          const nx = dx / d;
          const nz = dz / d;
          a.x -= nx * push;
          a.z -= nz * push;
          c.x += nx * push;
          c.z += nz * push;
        }
      }
    }
  }
  // ------------------------------------------------------------- contests
  tryPickupOrCatch() {
    const s = this.engine.state;
    const b = s.ball;
    if (b.mode !== "loose") return;
    const ballSpeed = Math.hypot(b.vx, b.vz);
    const groundPickup = b.y < 1.25 && ballSpeed < 9;
    const markCatch = b.y >= 1.8 && b.y < 2.65;
    if (!groundPickup && !markCatch) return;
    const candidates = s.players.filter(
      (p) => !p.onBench && !(p.id === this.kickGraceId && this.kickGraceT > 0) && Math.hypot(p.x - b.x, p.z - b.z) < CATCH_RADIUS && b.y < 2.65
    );
    if (candidates.length === 0) return;
    candidates.sort((a, c) => {
      const da = Math.hypot(a.x - b.x, a.z - b.z) - a.stats.marking * 0.35;
      const dc = Math.hypot(c.x - b.x, c.z - b.z) - c.stats.marking * 0.35;
      return da - dc;
    });
    const winner = candidates[0];
    const airborne = b.y > 0.85;
    if (airborne) {
      this.engine.onBallCaught(winner.id);
    } else {
      this.engine.onPossessionGained(winner.id);
    }
    this.runSinceBounce = 0;
    void this.rng;
  }
  tryTackles(carrier) {
    const s = this.engine.state;
    for (const p of s.players) {
      if (p.onBench || p.team === carrier.team || p.id === carrier.id) continue;
      const d = Math.hypot(p.x - carrier.x, p.z - carrier.z);
      if (d > TACKLE_RADIUS) continue;
      const isHumanTackle = p.id === this.controlledId;
      const aiTackleChance = this.difficulty === "afl" ? 0.1 : this.difficulty === "club" ? 0.07 : 0.045;
      if (!isHumanTackle && this.rng() > aiTackleChance) continue;
      const behind = (carrier.x - p.x) * Math.cos(carrier.facing) + (carrier.z - p.z) * Math.sin(carrier.facing) > 0.6;
      const ctx = {
        priorOpportunity: false,
        highContact: this.rng() < 0.035,
        backContact: behind && this.rng() < 0.12,
        incorrectDisposal: this.rng() < 0.02,
        attemptedDisposal: false,
        ballSpilledFree: false
      };
      this.engine.onTackle(p.id, carrier.id, ctx);
      return;
    }
  }
  handleGoalLine(side, before) {
    const s = this.engine.state;
    const b = s.ball;
    const crossX = side * FIELD.goalLineX;
    const t = (crossX - before.x) / (b.x - before.x || 1);
    const crossZ = before.z + (b.z - before.z) * Math.max(0, Math.min(1, t));
    const at = crossX > 0 ? 0 : 1;
    const defending = at === 0 ? 1 : 0;
    const lastTouchTeam = this.lastTouchTeam();
    const deliberateRush = lastTouchTeam === defending && (b.lastDisposal === "handball" || b.lastDisposal === "none");
    this.engine.onGoalLineCrossed(crossX, crossZ, { deliberateRush });
  }
  handleBoundary(before, b) {
    const lastTouchTeam = this.lastTouchTeam();
    const deliberate = b.lastDisposal === "none" && lastTouchTeam !== null && this.rng() < 0.25;
    this.engine.onBoundaryCrossed(before.x, before.z, { x: b.x, z: b.z }, false, deliberate);
  }
  lastTouchTeam() {
    const s = this.engine.state;
    const b = s.ball;
    if (b.holderId !== null) {
      return s.players.find((p) => p.id === b.holderId)?.team ?? null;
    }
    const byId = b.kickedById ?? b.handballedById;
    if (byId !== null) {
      return s.players.find((p) => p.id === byId)?.team ?? null;
    }
    return null;
  }
  // --------------------------------------------------------------- actions
  humanActions(carrier, human) {
    const s = this.engine.state;
    const b = s.ball;
    if (human.handball || human.kickReleased) {
      this.kickGraceId = carrier.id;
      this.kickGraceT = 0.85;
    }
    if (human.handball) {
      const dirX = Math.cos(carrier.facing);
      const dirZ = Math.sin(carrier.facing);
      this.engine.onKick(carrier.id, { handball: true });
      launchHandball(b, carrier.x + dirX * 0.5, 1.1, carrier.z + dirZ * 0.5, dirX, dirZ, 0.55, this.rng);
      this.runSinceBounce = 0;
      return;
    }
    if (human.kickReleased) {
      const power = 0.25 + this.kickCharge * 0.75;
      this.kickCharge = 0;
      const setShot = s.phase === "freeKick" && s.freeKick?.isSetShot;
      let dirX = Math.cos(carrier.facing);
      let dirZ = Math.sin(carrier.facing);
      if (setShot) {
        const goalX = attackGoalX(carrier.team);
        const dx = goalX - carrier.x;
        const dz = -carrier.z;
        const d = Math.hypot(dx, dz) || 1;
        dirX = dx / d;
        dirZ = dz / d;
        dirZ += human.aimZ * 0.12;
        const dist = Math.hypot(goalX - carrier.x, carrier.z);
        const p2 = Math.min(1, 0.5 + dist / 95 + this.kickCharge * 0.1);
        this.engine.onKick(carrier.id);
        const acc2 = carrier.stats.kicking * 0.9 + 0.1 - Math.min(0.35, dist / 160);
        launchKick(b, carrier.x + dirX * 0.5, 1.15, carrier.z + dirZ * 0.5, dirX, dirZ, p2, acc2, this.rng);
        this.runSinceBounce = 0;
        return;
      }
      const acc = carrier.stats.kicking * 0.82 + 0.16;
      this.engine.onKick(carrier.id);
      launchKick(b, carrier.x + dirX * 0.5, 1.15, carrier.z + dirZ * 0.5, dirX, dirZ, power, acc, this.rng);
      this.runSinceBounce = 0;
    }
  }
  tryAiActions(p, intent, ctx) {
    const s = this.engine.state;
    const b = s.ball;
    const isCarrier = b.mode === "held" && b.holderId === p.id;
    if (!isCarrier) return;
    if (intent.wantHandball || intent.wantKick) {
      this.kickGraceId = p.id;
      this.kickGraceT = 0.85;
    }
    if (intent.wantHandball) {
      this.engine.onKick(p.id, { handball: true });
      launchHandball(b, p.x, 1.1, p.z, intent.aimX, intent.aimZ, 0.6, this.rng);
      this.runSinceBounce = 0;
      return;
    }
    if (intent.wantKick && (this.liveTime > 0.45 || s.phase === "kickIn" || s.phase === "freeKick" && s.freeKick?.isSetShot)) {
      const setShot = s.phase === "freeKick" && s.freeKick?.isSetShot;
      const goalX = attackGoalX(p.team);
      const dist = setShot ? Math.hypot(goalX - p.x, p.z) : 40;
      const acc = p.stats.kicking * (this.difficulty === "afl" ? 0.9 : this.difficulty === "club" ? 0.8 : 0.68);
      const power = setShot ? Math.min(1, 0.55 + dist / 95) : intent.power;
      this.engine.onKick(p.id);
      launchKick(b, p.x, 1.15, p.z, intent.aimX, intent.aimZ, power, acc, this.rng);
      this.runSinceBounce = 0;
    }
    void ctx;
  }
  /** Extra event stream for camera/audio (goal celebrations etc). */
  recentEvents() {
    return this.eventsOut;
  }
  controlled() {
    return this.engine.state.players.find((p) => p.id === this.controlledId) ?? null;
  }
};
function humanToIntents(h, charge) {
  return {
    moveX: h.moveX,
    moveZ: h.moveZ,
    sprint: h.sprint,
    wantKick: h.kickReleased,
    wantHandball: h.handball,
    wantTackle: h.tackle,
    wantBounce: h.bounce,
    aimX: Math.abs(h.moveX) + Math.abs(h.moveZ) > 0.1 ? h.moveX : 1,
    aimZ: h.aimZ,
    power: 0.25 + charge * 0.75
  };
}

// tools/video/capture.ts
function settings(seed, quarterSeconds = 300) {
  return { seed, quarterSeconds, quarters: 4, interchange: 5, rotationCap: 75 };
}
var charging = 0;
function scriptedIntent(sim) {
  const it = { ...emptyHumanIntent() };
  const s = sim.state;
  const c = s.players.find((p) => p.id === sim.controlledId);
  if (!c) return it;
  const dirX = c.team === 0 ? 1 : -1;
  const b = s.ball;
  const distGoal = dirX > 0 ? 135 - c.x : c.x + 69;
  const pressured = s.players.some(
    (p) => p.team !== c.team && !p.onBench && Math.hypot(p.x - c.x, p.z - c.z) < 5
  );
  if (b.holderId === c.id) {
    if (charging > 0) {
      charging--;
      if (charging > 0) it.kickHeld = true;
      else it.kickReleased = true;
      it.aimZ = -c.z * 0.02 + (Math.random() - 0.5) * 0.15;
      return it;
    }
    it.moveX = dirX;
    it.moveZ = Math.max(-1, Math.min(1, -c.z * 0.04 + (Math.random() - 0.5) * 0.5));
    if (distGoal < 52 && Math.random() < 0.18) {
      charging = 12 + Math.floor(Math.random() * 8);
      it.kickHeld = true;
      it.aimZ = -c.z * 0.02 + (Math.random() - 0.5) * 0.15;
    } else if (pressured && Math.random() < 0.22) {
      if (Math.random() < 0.5) it.handball = true;
      else {
        charging = 8 + Math.floor(Math.random() * 6);
        it.kickHeld = true;
        it.aimZ = (Math.random() - 0.5) * 0.6;
      }
    }
  } else {
    charging = 0;
    const dx = b.x - c.x;
    const dz = b.z - c.z;
    const d = Math.hypot(dx, dz) || 1;
    it.moveX = dx / d;
    it.moveZ = dz / d;
    if (b.y > 1.6 && d < 5 && Math.random() < 0.1) it.tackle = true;
    it.sprint = d > 8;
  }
  return it;
}
function runSearch(seeds, seconds) {
  const results = [];
  for (let seed = 1; seed <= seeds; seed++) {
    const sim = new MatchSim(settings(seed));
    sim.start();
    let score = 0;
    let goals = 0;
    const steps = Math.floor(seconds * 60);
    for (let i = 0; i < steps; i++) {
      const evs = sim.update(1 / 60, scriptedIntent(sim));
      for (const e of evs) {
        if (e.type === "goal") {
          score += 60;
          goals++;
        } else if (e.type === "behind") score += 12;
        else if (e.type === "mark") score += 6;
        else if (e.type === "freeKick" || e.type === "fiftyMetres") score += 3;
        else if (e.type === "tackle") score += 1.5;
        else if (e.type === "stat") score += 0.4;
      }
    }
    results.push({ seed, score, goals });
  }
  results.sort((a, b) => b.goals - a.goals || b.score - a.score);
  const top = results[0];
  const ranked = results.slice(0, 6).map((r) => `seed ${r.seed}: ${r.goals} goals ${r.score.toFixed(0)}`).join(" | ");
  return { ...top, ranked };
}
function capture(seed, gameSeconds, fps) {
  const sim = new MatchSim(settings(seed));
  sim.start();
  const out = { fps, frames: [], goalFrames: [], eventFrames: [], seed };
  const perFrame = 60 / fps;
  const totalFrames = Math.floor(gameSeconds * fps);
  for (let f = 0; f < totalFrames; f++) {
    let toRun = Math.round((f + 1) * perFrame) - Math.round(f * perFrame);
    let events = [];
    while (toRun-- > 0) {
      events = events.concat(sim.update(1 / 60, scriptedIntent(sim)));
    }
    const s = sim.state;
    const c = s.players.find((p) => p.id === sim.controlledId);
    const clock = s.clock;
    const fr = {
      t: f / fps,
      ball: [r2(s.ball.x), r2(s.ball.y), r2(s.ball.z)],
      players: s.players.map((p) => [
        p.id,
        r2(p.x),
        r2(p.z),
        r2(p.y),
        r2(p.facing),
        r2(p.speed),
        animCode(p, sim)
      ]),
      controlledId: c ? c.id : -1,
      quarter: clock.quarter,
      clock: Math.max(0, clock.secondsRemaining),
      scores: [s.scores[0].goals * 6 + s.scores[0].behinds, s.scores[1].goals * 6 + s.scores[1].behinds],
      events: events.map((e) => ({
        type: e.type,
        text: e.text,
        team: e.team
      }))
    };
    if (events.some((e) => e.type === "goal")) out.goalFrames.push(f);
    if (events.length) out.eventFrames.push(f);
    out.frames.push(fr);
  }
  return out;
}
function animCode(p, sim) {
  const b = sim.state.ball;
  if (b.holderId === p.id) return 4;
  if (p.speed > 6.2) return 3;
  if (p.speed > 3.2) return 2;
  if (p.speed > 0.6) return 1;
  return 0;
}
function r2(n) {
  return Math.round(n * 100) / 100;
}
export {
  capture,
  runSearch
};
