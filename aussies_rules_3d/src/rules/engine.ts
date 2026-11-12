/**
 * RulesEngine — the authoritative match state machine.
 *
 * Owns the clock, scores, phases, free kicks and ball legality state; the
 * simulation (`src/sim`) drives player/ball motion and reports what happened,
 * and every decision is made here by the pure law functions in `laws.ts`.
 */
import {
  AFL_SETTINGS,
  BallState,
  FIELD,
  FreeKick,
  MatchEvent,
  MatchSettings,
  MatchState,
  PlayerRole,
  PlayerState,
  PlayerStats,
  TeamId,
  totalPoints,
} from './types';
import {
  attackGoalX,
  boundaryCrossing,
  clampInside,
  defendGoalX,
  isOutOfBounds,
  scoreAtCrossing,
} from './field';
import {
  applyFiftyMetrePenalty,
  applyScore,
  decideMark,
  decideOutOfBounds,
  decideRunTooFar,
  decideTackle,
  isSetShot,
  makeFreeKick,
  TackleContext,
} from './laws';

export interface RosterEntry {
  name: string;
  number: number;
  role: PlayerRole;
  stats: PlayerStats;
}

export const TEAM_NAMES: [string, string] = ['Melbourne', 'Collingwood'];

const ROLE_PLAN: PlayerRole[] = [
  'fullback', 'keyDefender', 'keyDefender', 'halfBack', 'halfBack', 'halfBack',
  'midfielder', 'midfielder', 'midfielder', 'midfielder', 'ruck', 'midfielder',
  'halfForward', 'halfForward', 'halfForward', 'keyForward', 'keyForward', 'fullForward',
];

const FIRST_NAMES = [
  'Jack', 'Tom', 'Liam', 'Noah', 'Oliver', 'Harry', 'Cooper', 'Bailey', 'Mitch', 'Luke',
  'Josh', 'Sam', 'Will', 'Charlie', 'Alex', 'Max', 'Ben', 'Jake', 'Toby', 'Oscar',
  'Hugh', 'Finn', 'Ned', 'Rory', 'Darcy', 'Jai', 'Kye', 'Lockie', 'Trent', 'Bailey',
];
const LAST_NAMES = [
  'McKenzie', 'Kelly', 'O’Brien', 'Smith', 'Jones', 'Brown', 'Williams', 'Wilson',
  'Taylor', 'Davies', 'Martin', 'Anderson', 'Walker', 'White', 'Thompson', 'Harris',
  'Nelson', 'Ryan', 'Bennett', 'Foster', 'Grant', 'Palmer', 'Walsh', 'Reid', 'Mills',
  'Pearce', 'Chen', 'Patel', 'Kowalski', 'Villa',
];

function statsFor(role: PlayerRole, rng: () => number): PlayerStats {
  const base = 0.55 + rng() * 0.35;
  const tweak = (v: number) => Math.min(1, Math.max(0.2, v));
  switch (role) {
    case 'ruck':
      return { speed: tweak(base - 0.12), strength: tweak(base + 0.25), kicking: tweak(base - 0.05), marking: tweak(base + 0.2), tackling: tweak(base + 0.1), endurance: tweak(base - 0.1) };
    case 'midfielder':
      return { speed: tweak(base + 0.12), strength: tweak(base), kicking: tweak(base + 0.1), marking: tweak(base - 0.05), tackling: tweak(base + 0.08), endurance: tweak(base + 0.2) };
    case 'keyForward':
    case 'fullForward':
      return { speed: tweak(base), strength: tweak(base + 0.15), kicking: tweak(base + 0.18), marking: tweak(base + 0.22), tackling: tweak(base - 0.05), endurance: tweak(base - 0.05) };
    case 'keyDefender':
    case 'fullback':
      return { speed: tweak(base), strength: tweak(base + 0.15), kicking: tweak(base + 0.05), marking: tweak(base + 0.18), tackling: tweak(base + 0.12), endurance: tweak(base) };
    default:
      return { speed: tweak(base + 0.08), strength: tweak(base), kicking: tweak(base + 0.12), marking: tweak(base + 0.05), tackling: tweak(base + 0.05), endurance: tweak(base + 0.1) };
  }
}

export function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function buildRoster(team: TeamId, seed: number, bench: number): RosterEntry[] {
  const rng = mulberry32(seed * 1000 + team * 101 + 7);
  const roster: RosterEntry[] = [];
  for (let i = 0; i < 18 + bench; i++) {
    const role = i < 18 ? ROLE_PLAN[i] : 'midfielder';
    roster.push({
      name: `${FIRST_NAMES[Math.floor(rng() * FIRST_NAMES.length)]} ${LAST_NAMES[Math.floor(rng() * LAST_NAMES.length)]}`,
      number: i + 1 + team * 20,
      role,
      stats: statsFor(role, rng),
    });
  }
  return roster;
}

interface PossessionMeta {
  holderSince: number;
  priorOpportunity: boolean;
  metresSinceBounce: number;
  shrugOrFend: boolean;
}

export class RulesEngine {
  state: MatchState;
  private rng: () => number;
  private possession: PossessionMeta = {
    holderSince: 0,
    priorOpportunity: false,
    metresSinceBounce: 0,
    shrugOrFend: false,
  };
  private phaseTimer = 0;
  private kickInTimer = 0;
  private celebrationIsGoal = false;
  private celebrationDefendingTeam: TeamId = 1;

  constructor(settings: MatchSettings = AFL_SETTINGS) {
    this.rng = mulberry32(settings.seed);
    this.state = {
      settings,
      clock: { quarter: 1, secondsRemaining: settings.quarterSeconds, running: false, timeOn: 0 },
      scores: [{ goals: 0, behinds: 0 }, { goals: 0, behinds: 0 }],
      ball: this.freshBall(),
      players: [],
      phase: 'preMatch',
      freeKick: null,
      restartX: 0,
      restartZ: 0,
      nominatedRucks: [null, null],
      rotations: [0, 0],
      events: [],
      winner: null,
      setShotDeadline: 0,
    };
  }

  private freshBall(): BallState {
    return {
      x: 0, y: 0.3, z: 0,
      vx: 0, vy: 0, vz: 0,
      spin: 0,
      mode: 'dead',
      holderId: null,
      kickedById: null,
      kickedFromX: 0,
      kickedFromZ: 0,
      kickDistance: 0,
      kickedAt: 0,
      touched: false,
      bounced: false,
      lastDisposal: 'none',
      handballedById: null,
    };
  }

  // ------------------------------------------------------------------ setup

  buildTeams(rosters?: [RosterEntry[], RosterEntry[]]): void {
    const [home, away] = rosters ?? [
      buildRoster(0, this.state.settings.seed, this.state.settings.interchange),
      buildRoster(1, this.state.settings.seed, this.state.settings.interchange),
    ];
    this.state.players = [];
    for (const team of [0, 1] as TeamId[]) {
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
          sprintRamp: 0,
          tackleCooldown: 0,
          x: 0,
          z: 0,
          y: 0,
          vx: 0,
          vy: 0,
          vz: 0,
          facing: team === 0 ? 0 : Math.PI,
          onBench: i >= 18,
        });
      });
    }
  }

  startMatch(): void {
    this.state.clock.quarter = 1;
    this.state.clock.secondsRemaining = this.state.settings.quarterSeconds;
    this.state.scores = [{ goals: 0, behinds: 0 }, { goals: 0, behinds: 0 }];
    this.beginQuarter();
    this.emit({ type: 'centreBallUp', x: 0, z: 0 });
  }

  private beginQuarter(): void {
    this.state.clock.running = false;
    this.state.clock.timeOn = 0;
    this.state.phase = 'centreBallUp';
    this.phaseTimer = 1.6;
    this.state.restartX = 0;
    this.state.restartZ = 0;
    this.setupSixSixSix();
  }

  /** Place players in the 6-6-6 formation for a centre ball-up. */
  setupSixSixSix(): void {
    for (const team of [0, 1] as TeamId[]) {
      const dir = team === 0 ? 1 : -1;
      const on = this.state.players.filter((p) => p.team === team && !p.onBench);
      // 6 inside each 50 arc, 6 in the middle (6-6-6; 2026: no goal-square player)
      const slots: { x: number; z: number }[] = [];
      for (let i = 0; i < 6; i++) {
        const ang = -0.9 + (i / 5) * 1.8;
        slots.push({ x: dir * (FIELD.goalLineX - 32 + Math.cos(ang) * 12), z: Math.sin(ang) * 34 });
      }
      for (let i = 0; i < 6; i++) {
        const ang = -0.9 + (i / 5) * 1.8;
        slots.push({ x: -dir * (FIELD.goalLineX - 32 + Math.cos(ang) * 12), z: Math.sin(ang) * 34 });
      }
      const mid = [
        { x: dir * 3, z: 0 }, { x: dir * 12, z: -14 }, { x: dir * 12, z: 14 },
        { x: dir * 24, z: -22 }, { x: dir * 24, z: 22 }, { x: dir * 20, z: 0 },
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

  step(dt: number): void {
    const s = this.state;
    const phaseAtStart = s.phase;

    switch (s.phase) {
      case 'centreBallUp':
      case 'ballUp':
      case 'throwIn':
        this.phaseTimer -= dt;
        if (this.phaseTimer <= 0) this.completeRestart();
        break;
      case 'scoreCelebration':
        this.phaseTimer -= dt;
        if (this.phaseTimer <= 0) this.completeCelebration();
        break;
      case 'quarterBreak':
        this.phaseTimer -= dt;
        if (this.phaseTimer <= 0) this.startNextQuarter();
        break;
      case 'freeKick':
      case 'kickIn':
        if (s.freeKick) {
          s.freeKick.shotClock -= dt;
          if (s.phase === 'kickIn') this.kickInTimer += dt;
          if (s.freeKick.shotClock <= 0) this.shotClockExpired();
        }
        break;
      default:
        break;
    }

    // The 20-minute clock runs while the ball is live (and while a free kick
    // is being taken — matches "20 min + time on", where the clock stops for
    // scores, quarter breaks and injuries). The clock state at the START of
    // the step decides, so a restart completed mid-step doesn't eat time.
    const running =
      phaseAtStart === 'live' ||
      phaseAtStart === 'freeKick' ||
      phaseAtStart === 'kickIn' ||
      phaseAtStart === 'ballUp' ||
      phaseAtStart === 'throwIn';
    s.clock.running = running || s.phase === 'live';
    if (running) {
      s.clock.secondsRemaining -= dt;
      if (s.clock.secondsRemaining <= 0) {
        s.clock.secondsRemaining = 0;
        this.endQuarter();
      }
    } else if (
      phaseAtStart !== 'quarterBreak' &&
      phaseAtStart !== 'preMatch' &&
      phaseAtStart !== 'matchEnd'
    ) {
      s.clock.timeOn += dt;
    }

    // Prior opportunity accrues while holding the ball (0.35 s, or a shrug).
    const b = s.ball;
    if (b.mode === 'held' && b.holderId !== null) {
      if (s.clock.secondsRemaining >= 0 && this.possession.holderSince >= 0) {
        const held = this.elapsedHeld();
        if (held > 0.35) this.possession.priorOpportunity = true;
      }
    }
  }

  private elapsedHeld(): number {
    return this.state.settings.quarterSeconds - this.state.clock.secondsRemaining - this.possession.holderSince;
  }

  // ------------------------------------------------------------ restarts

  private completeRestart(): void {
    const s = this.state;
    const b = s.ball;
    b.mode = 'loose';
    b.holderId = null;
    b.lastDisposal = 'none';
    b.touched = false;
    b.bounced = false;
    b.kickDistance = 0;
    b.x = s.restartX;
    b.z = s.restartZ;
    b.y = 2.1;
    b.vx = (this.rng() - 0.5) * 1.5;
    b.vy = 1.2;
    b.vz = (this.rng() - 0.5) * 1.5;
    s.phase = 'live';
    s.freeKick = null;
  }

  private completeCelebration(): void {
    const s = this.state;
    if (s.phase === 'matchEnd') return;
    // Goal → centre ball-up. Behind → kick-in by the defending team.
    if (!this.celebrationIsGoal) {
      this.startKickIn(this.celebrationDefendingTeam);
    } else {
      s.phase = 'centreBallUp';
      this.phaseTimer = 1.4;
      s.restartX = 0;
      s.restartZ = 0;
      this.setupSixSixSix();
    }
  }

  startKickIn(defendingTeam: TeamId): void {
    const s = this.state;
    const gx = defendGoalX(defendingTeam);
    s.phase = 'kickIn';
    this.kickInTimer = 0;
    const taker = this.nearestPlayer(defendingTeam, gx, 0, true);
    const spot = clampInside(gx + (defendingTeam === 0 ? 6 : -6), 0);
    if (taker) {
      taker.x = spot.x;
      taker.z = spot.z;
      this.giveBallTo(taker.id);
    }
    s.freeKick = makeFreeKick(defendingTeam, taker ? taker.id : -1, spot.x, spot.z, 'advantage', {
      shotClock: FIELD.restartSeconds,
    });
    this.emit({ type: 'kickIn', team: defendingTeam, playerId: taker?.id, x: spot.x, z: spot.z });
  }

  startBallUp(x: number, z: number, throwIn = false): void {
    const s = this.state;
    const spot = clampInside(x, z);
    s.restartX = spot.x;
    s.restartZ = spot.z;
    s.phase = throwIn ? 'throwIn' : 'ballUp';
    this.phaseTimer = throwIn ? 1.1 : 0.8;
    s.freeKick = null;
    const b = s.ball;
    b.mode = 'dead';
    b.holderId = null;
    b.x = spot.x;
    b.z = spot.z;
    b.y = 2.0;
    this.emit({ type: throwIn ? 'throwIn' : 'ballUp', x: spot.x, z: spot.z });
  }

  /** Bring the ball back into play after a mark or free kick. */
  awardFreeKick(fk: FreeKick): void {
    const s = this.state;
    s.freeKick = fk;
    s.phase = 'freeKick';
    s.clock.running = true;
    const taker = s.players.find((p) => p.id === fk.takerId);
    if (taker) {
      taker.x = fk.x;
      taker.z = fk.z;
      this.giveBallTo(taker.id);
    } else if (s.players.length > 0) {
      // pick the nearest eligible player to take it
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
      type: 'freeKick',
      team: fk.team,
      playerId: fk.takerId,
      x: fk.x,
      z: fk.z,
      text: fk.reason,
    });
    if (fk.fiftyMetres) this.emit({ type: 'fiftyMetres', team: fk.team, playerId: fk.takerId });
    if (fk.isMark) this.emit({ type: 'mark', team: fk.team, playerId: fk.takerId });
  }

  private shotClockExpired(): void {
    const s = this.state;
    const fk = s.freeKick;
    if (!fk) return;
    // Delay of play: umpire balls it up (or, on a kick-in, free kick against).
    if (s.phase === 'kickIn') {
      const other: TeamId = fk.team === 0 ? 1 : 0;
      const spot = clampInside(fk.x, fk.z);
      this.awardFreeKick(
        makeFreeKick(other, -1, spot.x, spot.z, 'kickInNotCleared')
      );
      return;
    }
    this.startBallUp(fk.x, fk.z);
    this.emit({ type: 'hold', text: 'Time!' });
  }

  // ------------------------------------------------------------- possession

  giveBallTo(playerId: number): void {
    const s = this.state;
    const p = s.players.find((x) => x.id === playerId);
    if (!p) return;
    const b = s.ball;
    b.mode = 'held';
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
      shrugOrFend: false,
    };
  }

  /** Player gained possession in open play (pickup or short handball receive). */
  onPossessionGained(playerId: number): void {
    const wasLive = this.state.phase === 'live';
    this.giveBallTo(playerId);
    if (!wasLive && (this.state.phase === 'freeKick' || this.state.phase === 'kickIn')) {
      // picked up during a set-up — ignore
      return;
    }
  }

  onBounce(playerId: number): void {
    if (this.state.ball.holderId === playerId) {
      this.possession.metresSinceBounce = 0;
    }
    this.state.ball.bounced = true;
    this.emit({ type: 'stat', playerId, text: 'bounce' });
  }

  onTouchDown(playerId: number): void {
    if (this.state.ball.holderId === playerId) {
      this.possession.metresSinceBounce = 0;
    }
  }

  onShrugOrFend(playerId: number): void {
    if (this.state.ball.holderId === playerId) {
      this.possession.shrugOrFend = true;
      this.possession.priorOpportunity = true; // 2026: a shrug is prior opportunity
    }
  }

  /** Accumulate run-with-ball distance; enforces the 15 m bounce law. */
  onRunMetres(playerId: number, metres: number): void {
    const b = this.state.ball;
    if (b.holderId !== playerId) return;
    this.possession.metresSinceBounce += metres;
    const call = decideRunTooFar(this.possession.metresSinceBounce, false);
    if (call.kind === 'freeKick') {
      const p = this.state.players.find((x) => x.id === playerId);
      if (p) {
        const other: TeamId = p.team === 0 ? 1 : 0;
        this.awardFreeKick(makeFreeKick(other, -1, p.x, p.z, 'runningTooFar'));
        this.emit({ type: 'freeKick', team: other, text: 'runningTooFar', x: p.x, z: p.z });
      }
    }
  }

  onKick(playerId: number, opts: { handball?: boolean } = {}): void {
    const s = this.state;
    const b = s.ball;
    const p = s.players.find((x) => x.id === playerId);
    if (!p) return;
    b.mode = 'loose';
    b.holderId = null;
    b.lastDisposal = opts.handball ? 'handball' : 'kick';
    b.kickedById = playerId;
    b.handballedById = opts.handball ? playerId : null;
    b.kickedFromX = p.x;
    b.kickedFromZ = p.z;
    b.kickDistance = 0;
    b.touched = false;
    b.bounced = false;
    b.kickedAt = s.settings.quarterSeconds - s.clock.secondsRemaining;
    if (s.phase === 'freeKick' || s.phase === 'kickIn') {
      s.phase = 'live';
      s.freeKick = null;
      this.emit({ type: 'playOn', playerId });
    }
    this.possession.metresSinceBounce = 0;
    this.emit({ type: 'stat', playerId, text: opts.handball ? 'handball' : 'kick' });
  }

  /** Ball caught in flight — checks the mark. */
  onBallCaught(playerId: number): void {
    const s = this.state;
    const p = s.players.find((x) => x.id === playerId);
    if (!p) return;
    // Snapshot the flight BEFORE giving up the ball (giveBallTo resets meta).
    const snapshot: BallState = { ...s.ball, mode: 'held', holderId: playerId };
    const decision = decideMark(snapshot, p);
    this.giveBallTo(playerId);
    if (decision.kind === 'mark') {
      this.emit({ type: 'mark', team: p.team, playerId, x: p.x, z: p.z });
      this.awardFreeKick(
        makeFreeKick(p.team, playerId, p.x, p.z, 'mark', { isMark: true })
      );
    }
  }

  onTackle(tacklerId: number, carrierId: number, ctx: TackleContext): void {
    const s = this.state;
    const tackler = s.players.find((p) => p.id === tacklerId);
    const carrier = s.players.find((p) => p.id === carrierId);
    if (!tackler || !carrier) return;

    const prior = this.possession.priorOpportunity || this.possession.shrugOrFend;
    const decision = decideTackle(tackler, carrier, {
      ...ctx,
      priorOpportunity: prior || ctx.priorOpportunity,
    });

    switch (decision.kind) {
      case 'holdingTheBall':
      case 'incorrectDisposal':
        this.emit({ type: 'tackle', playerId: tacklerId, x: carrier.x, z: carrier.z });
        this.awardFreeKick(
          makeFreeKick(tackler.team, tacklerId, carrier.x, carrier.z,
            decision.kind === 'holdingTheBall' ? 'holdingTheBall' : 'throwing')
        );
        break;
      case 'highTackle':
      case 'pushInTheBack':
        this.emit({ type: 'tackle', playerId: tacklerId });
        this.awardFreeKick(
          makeFreeKick(carrier.team, carrierId, carrier.x, carrier.z,
            decision.kind === 'highTackle' ? 'highTackle' : 'pushInTheBack')
        );
        break;
      case 'legalTacklePlayOn': {
        this.emit({ type: 'tackle', playerId: tacklerId });
        this.giveBallTo(tacklerId);
        break;
      }
      case 'noPriorBallUp':
        this.emit({ type: 'tackle', playerId: tacklerId });
        this.startBallUp(carrier.x, carrier.z);
        break;
    }
  }

  /** An opponent infringed inside the protected area or interfered → 50 m. */
  onProtectedAreaBreach(playerId: number): void {
    const s = this.state;
    const fk = s.freeKick;
    if (!fk) return;
    const p = s.players.find((x) => x.id === playerId);
    if (!p || p.team === fk.team) return;
    const upgraded = applyFiftyMetrePenalty(fk);
    upgraded.reason = 'protectedArea';
    this.awardFreeKick(upgraded);
    this.emit({ type: 'fiftyMetres', team: fk.team, playerId: fk.takerId });
  }

  onInterferenceAfterMark(playerId: number): void {
    this.onProtectedAreaBreach(playerId);
  }

  // ------------------------------------------------------------ ball flight

  /** Called by the sim each frame the ball is loose: tracks flight distance. */
  onBallFlight(dt: number): void {
    const b = this.state.ball;
    if (b.mode === 'loose' && b.lastDisposal !== 'none') {
      b.kickDistance += Math.hypot(b.vx, b.vy, b.vz) * dt;
    }
  }

  onBallTouched(playerId: number): void {
    this.state.ball.touched = true;
    this.emit({ type: 'touch', playerId });
  }

  onBallBounced(): void {
    this.state.ball.bounced = true;
    this.state.ball.kickDistance = 0; // a bounce ends the "air distance"
    this.state.ball.touched = this.state.ball.touched || false;
    // After the bounce the ball can no longer be marked, and OOB rules change.
  }

  /**
   * The whole ball crossed the boundary line (not the goal line).
   * `prev` is the previous in-bounds position for the crossing point.
   */
  onBoundaryCrossed(
    prevX: number,
    prevZ: number,
    crossed: { x: number; z: number },
    smotheredOrDeflected: boolean,
    deliberate: boolean
  ): void {
    const s = this.state;
    const b = s.ball;
    const crossing = boundaryCrossing(prevX, prevZ, crossed.x, crossed.z);
    const holder = b.holderId !== null ? s.players.find((p) => p.id === b.holderId) : null;
    const lastTouchTeam: TeamId | null =
      holder?.team ??
      (b.kickedById !== null
        ? s.players.find((p) => p.id === b.kickedById)?.team ?? null
        : null);

    const decision = decideOutOfBounds(
      b,
      crossing.x,
      crossing.z,
      lastTouchTeam,
      smotheredOrDeflected,
      deliberate
    );
    b.mode = 'dead';
    b.holderId = null;

    switch (decision.kind) {
      case 'outOnTheFull':
      case 'lastDisposal':
      case 'deliberate': {
        this.emit({
          type: decision.kind === 'outOnTheFull' ? 'outOnTheFull' : 'lastDisposal',
          team: decision.toTeam,
          x: decision.x,
          z: decision.z,
          text: decision.kind,
        });
        const taker = this.nearestPlayer(decision.toTeam, decision.x, decision.z, true);
        this.awardFreeKick(
          makeFreeKick(decision.toTeam, taker ? taker.id : -1, decision.x, decision.z,
            decision.kind === 'outOnTheFull'
              ? 'outOnTheFull'
              : decision.kind === 'lastDisposal'
                ? 'lastDisposalOOB'
                : 'deliberateOOB')
        );
        break;
      }
      case 'throwIn':
        this.startBallUp(decision.x, decision.z, true);
        break;
    }
    void isOutOfBounds;
  }

  /**
   * The ball crossed the goal line (between the behind posts) or hit a post.
   * `endX` sign: +1 = east goal line, -1 = west.
   */
  onGoalLineCrossed(
    crossX: number,
    crossZ: number,
    opts: { postHit?: 'goalPost' | 'behindPost'; deliberateRush?: boolean } = {}
  ): void {
    const s = this.state;
    const b = s.ball;
    const at = scoreAtCrossing(crossX, crossZ);
    if (!at) return;

    const scoringTeam: TeamId = crossX > 0 ? 0 : 1;
    const otherTeam: TeamId = scoringTeam === 0 ? 1 : 0;

    b.mode = 'dead';
    b.holderId = null;

    if (opts.postHit === 'behindPost') {
      if (!b.bounced) {
        // behind post on the full → free kick to the opposition beside the post
        this.emit({ type: 'outOnTheFull', team: otherTeam, x: crossX, z: crossZ });
        const taker = this.nearestPlayer(otherTeam, crossX, crossZ, true);
        this.awardFreeKick(
          makeFreeKick(otherTeam, taker ? taker.id : -1, crossX, crossZ, 'outOnTheFull')
        );
      } else {
        this.startBallUp(crossX, crossZ, true);
      }
      return;
    }

    if (opts.postHit === 'goalPost') {
      applyScore(s.scores, { kind: 'goalPost', behindTeam: scoringTeam });
      this.emit({ type: 'behind', team: scoringTeam, points: 1, x: crossX, z: crossZ });
      this.celebrate(false, otherTeam);
      return;
    }

    const isGoal =
      at.kind === 'goal' &&
      !b.touched &&
      b.lastDisposal === 'kick';

    if (isGoal) {
      applyScore(s.scores, { kind: 'goal', team: scoringTeam, points: 6 });
      this.emit({ type: 'goal', team: scoringTeam, points: 6, x: crossX, z: crossZ });
      this.celebrate(true, otherTeam);
      return;
    }

    // behind
    applyScore(s.scores, { kind: 'behind', team: scoringTeam, points: 1 });
    this.emit({ type: 'behind', team: scoringTeam, points: 1, x: crossX, z: crossZ });
    if (opts.deliberateRush) {
      // deliberate rushed behind: free kick to the attacking team, 15 m out
      // from the goal line they are attacking, directly in front.
      const gx = attackGoalX(scoringTeam);
      const spot = clampInside(gx - Math.sign(gx) * 15, 0);
      this.emit({ type: 'freeKick', team: scoringTeam, text: 'deliberateRushedBehind' });
      const taker = this.nearestPlayer(scoringTeam, spot.x, spot.z, true);
      this.awardFreeKick(
        makeFreeKick(scoringTeam, taker ? taker.id : -1, spot.x, spot.z, 'deliberateRushedBehind')
      );
      return;
    }
    this.celebrate(false, otherTeam);
  }

  private celebrate(wasGoal: boolean, defendingTeam: TeamId): void {
    const s = this.state;
    s.phase = 'scoreCelebration';
    this.phaseTimer = 3.2;
    this.celebrationIsGoal = wasGoal;
    this.celebrationDefendingTeam = defendingTeam;
    s.clock.running = false;
    this.emit({ type: 'siren', text: 'score' });
  }

  // ------------------------------------------------------------- quarters

  private endQuarter(): void {
    const s = this.state;
    s.phase = 'quarterBreak';
    s.clock.running = false;
    this.phaseTimer = 6.0;
    s.ball.mode = 'dead';
    s.ball.holderId = null;
    this.emit({ type: 'quarterEnd', text: `Q${s.clock.quarter}` });
    if (s.clock.quarter >= s.settings.quarters) {
      this.emit({ type: 'siren', text: 'final' });
    }
  }

  private startNextQuarter(): void {
    const s = this.state;
    if (s.clock.quarter >= s.settings.quarters) {
      s.phase = 'matchEnd';
      const m = totalPoints(s.scores[0]) - totalPoints(s.scores[1]);
      s.winner = m === 0 ? null : m > 0 ? 0 : 1;
      this.emit({ type: 'matchEnd', text: s.winner === null ? 'draw' : `team${s.winner}` });
      return;
    }
    s.clock.quarter += 1;
    s.clock.secondsRemaining = s.settings.quarterSeconds;
    s.clock.timeOn = 0;
    this.beginQuarter();
    this.emit({ type: 'centreBallUp', x: 0, z: 0 });
  }

  // -------------------------------------------------------------- utilities

  nearestPlayer(team: TeamId, x: number, z: number, excludeBench = true): PlayerState | null {
    let best: PlayerState | null = null;
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

  nearestToBall(): PlayerState | null {
    const b = this.state.ball;
    return this.nearestPlayer(0, b.x, b.z) ?? this.nearestPlayer(1, b.x, b.z);
  }

  callPlayOn(): void {
    const s = this.state;
    if (s.phase === 'freeKick' || s.phase === 'kickIn') {
      s.phase = 'live';
      s.freeKick = null;
      this.emit({ type: 'playOn' });
    }
  }

  drainEvents(): MatchEvent[] {
    const ev = this.state.events;
    this.state.events = [];
    return ev;
  }

  emit(e: MatchEvent): void {
    this.state.events.push(e);
  }

  /** Human/AI helper: where should a kick for goal be aimed? */
  targetGoalPoint(team: TeamId): { x: number; z: number } {
    return { x: attackGoalX(team), z: 0 };
  }
}
