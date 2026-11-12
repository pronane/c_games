/**
 * MatchSim — the gameplay layer: player kinematics, ball physics, contests,
 * tackles and the human control model, all driven through the RulesEngine so
 * every outcome follows the laws of the game.
 */
import {
  BallState,
  FIELD,
  MatchEvent,
  MatchSettings,
  PlayerState,
  TeamId,
} from '../rules/types';
import { attackGoalX, clampInside, defendGoalX, isOutOfBounds } from '../rules/field';
import { RulesEngine } from '../rules/engine';
import { launchHandball, launchKick, stepBall, predictDrop } from './ball';
import { AiContext, AiIntent, Difficulty, aiIntentFor, emptyIntent } from './ai';
import { mulberry32 } from '../rules/engine';

export interface HumanIntent {
  moveX: number;
  moveZ: number;
  sprint: boolean;
  kickHeld: boolean;
  kickReleased: boolean;
  handball: boolean;
  tackle: boolean;
  switchPlayer: boolean;
  bounce: boolean;
  /** Aim offset -1..1 (set shots): positive aims toward +z. */
  aimZ: number;
}

export function emptyHumanIntent(): HumanIntent {
  return {
    moveX: 0, moveZ: 0, sprint: false,
    kickHeld: false, kickReleased: false,
    handball: false, tackle: false, switchPlayer: false, bounce: false,
    aimZ: 0,
  };
}

const CATCH_RADIUS = 1.45;
const CPU_TACKLE_RANGE = 2.3;
const CPU_TACKLE_COMMIT_TIME = 0.3;
const CPU_TACKLE_COOLDOWN = 0.9;
const HUMAN_TACKLE_RADIUS = 2.15;
// Keep bodies from stacking, but stay below the tackle range (1.55 m) so the
// contest resolves — and resolve softly so a standing player isn't bulldozed.
const SEPARATION_RADIUS = 0.85;


/** Squared intent magnitude (no sqrt) — cheap ramp gate. */
function mag2(intent: { moveX: number; moveZ: number }): number {
  return intent.moveX * intent.moveX + intent.moveZ * intent.moveZ;
}

/** Distance from point (px,pz) to segment (ax,az)-(bx,bz). */
function pointSegDist(px: number, pz: number, ax: number, az: number, bx: number, bz: number): number {
  const abx = bx - ax;
  const abz = bz - az;
  const len2 = abx * abx + abz * abz;
  if (len2 < 1e-6) return Math.hypot(px - ax, pz - az);
  let t = ((px - ax) * abx + (pz - az) * abz) / len2;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(px - (ax + abx * t), pz - (az + abz * t));
}

export class MatchSim {
  engine: RulesEngine;
  difficulty: Difficulty;
  humanTeam: TeamId;
  controlledId: number;
  kickCharge = 0;
  private rng: () => number;
  private liveTime = 0;
  private cpuTackleTimer = 0;
  private runSinceBounce = 0;
  private eventsOut: MatchEvent[] = [];
  /** Player who last disposed of the ball; can't regather it briefly (smother/protection). */
  private kickGraceId = -1;
  private kickGraceT = 0;
  /** Attract/demo mode — both sides play themselves (menu backdrop). */
  attract = false;
  /** Gaelic-style assisted targets for the human carrier — -1 when none. */
  handTargetId = -1;
  kickTargetId = -1;
  /** Increments every control change — the renderer flashes a ring on it. */
  switchCount = 0;
  private switchLockT = 0;
  private looseSwitchCooldown = 0;
  private walkIds: number[] = [];
  private walkIndex = 0;
  private walkTimer = 0;

  constructor(settings: MatchSettings, difficulty: Difficulty = 'afl', humanTeam: TeamId = 0) {
    this.engine = new RulesEngine(settings);
    this.difficulty = difficulty;
    this.humanTeam = humanTeam;
    this.rng = mulberry32(settings.seed ^ 0x5f5f);
    this.controlledId = -1;
  }

  start(): void {
    this.engine.buildTeams();
    this.engine.startMatch();
    this.pickControlled(true);
  }

  get state() {
    return this.engine.state;
  }

  // ------------------------------------------------------------- control

  pickControlled(force = false): void {
    if (this.attract) {
      this.controlledId = -1;
      return;
    }
    const s = this.engine.state;
    const b = s.ball;
    const candidates = s.players.filter((p) => p.team === this.humanTeam && !p.onBench);
    if (candidates.length === 0) return;

    // Free kicks / kick-ins to the human team: control the taker.
    if (s.freeKick && s.freeKick.team === this.humanTeam && s.freeKick.takerId >= 0) {
      const taker = candidates.find((p) => p.id === s.freeKick!.takerId);
      if (taker) {
        this.setControlled(taker.id);
        return;
      }
    }

    const carrier =
      b.mode === 'held' && b.holderId !== null
        ? s.players.find((p) => p.id === b.holderId) ?? null
        : null;

    // Instant takeover when our team wins the ball — the core FIFA rule.
    if (carrier && carrier.team === this.humanTeam) {
      if (this.controlledId !== carrier.id) this.setControlled(carrier.id);
      return;
    }

    // Defence: best goal-side defender (or hold our manual pick while locked).
    if (carrier && carrier.team !== this.humanTeam) {
      if (this.switchLockT > 0 && !force) return;
      const pick = this.bestGoalSideDefender(candidates, carrier);
      if (pick && pick.id !== this.controlledId) this.setControlled(pick.id);
      return;
    }

    // Loose / high ball: best arrival-time estimate with hysteresis + cooldown.
    if (b.mode === 'loose') {
      if (this.looseSwitchCooldown > 0 && !force) return;
      const current = candidates.find((p) => p.id === this.controlledId);
      const curScore = current ? this.arrivalScore(current, b) : Infinity;
      let best = candidates[0];
      let bestScore = Infinity;
      for (const p of candidates) {
        const score = this.arrivalScore(p, b);
        if (score < bestScore) {
          bestScore = score;
          best = p;
        }
      }
      if (force || bestScore < curScore * 0.82 || !current) {
        if (best.id !== this.controlledId) {
          this.setControlled(best.id);
          this.looseSwitchCooldown = 1.0;
        }
      }
      return;
    }

    if (force) {
      const nearest = candidates.reduce((a, c) =>
        (a.x - b.x) ** 2 + (a.z - b.z) ** 2 < (c.x - b.x) ** 2 + (c.z - b.z) ** 2 ? a : c);
      this.setControlled(nearest.id);
    }
  }

  /** The one place control actually changes — bumps the switch flash counter. */
  private setControlled(id: number): void {
    if (this.controlledId !== id) {
      this.controlledId = id;
      this.switchCount++;
    }
  }

  /** Arrival-time estimate for a loose ball (seconds-weighted distance). */
  private arrivalScore(p: PlayerState, b: BallState): number {
    const relX = b.x - p.x;
    const relZ = b.z - p.z;
    const v2 = b.vx * b.vx + b.vz * b.vz;
    let t = 0;
    if (v2 > 1) t = Math.max(0, Math.min(3, -(relX * b.vx + relZ * b.vz) / v2));
    const px = b.x + b.vx * t - p.x;
    const pz = b.z + b.vz * t - p.z;
    return Math.hypot(px, pz) + t * 0.35;
  }

  /** Point-segment distance from a player to the carrier→goal line. */
  private bestGoalSideDefender(candidates: PlayerState[], carrier: PlayerState): PlayerState | null {
    const gx = defendGoalX(this.humanTeam);
    let best: PlayerState | null = null;
    let bestScore = Infinity;
    for (const p of candidates) {
      const dSeg = pointSegDist(p.x, p.z, carrier.x, carrier.z, gx, 0);
      const dBall = Math.hypot(p.x - carrier.x, p.z - carrier.z);
      const score = dSeg * 1.15 + dBall * 0.35;
      if (score < bestScore) {
        bestScore = score;
        best = p;
      }
    }
    return best;
  }

  switchPlayer(): void {
    if (this.attract) return;
    const s = this.engine.state;
    const b = s.ball;
    const candidates = s.players
      .filter((p) => p.team === this.humanTeam && !p.onBench && p.id !== this.controlledId)
      .sort(
        (a, c) =>
          (a.x - b.x) ** 2 + (a.z - b.z) ** 2 - ((c.x - b.x) ** 2 + (c.z - b.z) ** 2)
      );
    if (candidates.length === 0) return;
    // tap repeatedly to walk through the nearest options (1.2 s window)
    if (this.walkTimer > 0 && this.walkIds.length > 1) {
      this.walkIndex = (this.walkIndex + 1) % this.walkIds.length;
    } else {
      this.walkIds = candidates.map((c) => c.id);
      this.walkIndex = 0;
    }
    this.walkTimer = 1.2;
    this.switchLockT = 2.0;
    this.setControlled(this.walkIds[this.walkIndex]);
  }

  // -------------------------------------------------------------- update

  update(dt: number, human: HumanIntent): MatchEvent[] {
    dt = Math.min(dt, 1 / 20); // clamp long frames
    const s = this.engine.state;
    const b = s.ball;
    this.eventsOut = [];
    if (this.kickGraceT > 0) this.kickGraceT -= dt;
    if (this.switchLockT > 0) this.switchLockT -= dt;
    if (this.looseSwitchCooldown > 0) this.looseSwitchCooldown -= dt;
    if (this.walkTimer > 0) this.walkTimer -= dt;

    const wasPhase = s.phase;
    this.engine.step(dt);
    if (s.phase !== wasPhase) {
      this.liveTime = 0;
      this.pickControlled();
    } else {
      this.liveTime += dt;
    }

    if (s.phase === 'matchEnd') {
      this.eventsOut = this.engine.drainEvents();
      return this.eventsOut;
    }

    if (human.switchPlayer) this.switchPlayer();

    const carrier =
      b.mode === 'held' && b.holderId !== null
        ? s.players.find((p) => p.id === b.holderId) ?? null
        : null;

    const ctx: AiContext = {
      state: s,
      difficulty: this.difficulty,
      possessingTeam: carrier ? carrier.team : null,
      carrierId: carrier ? carrier.id : null,
      liveTime: this.liveTime,
      rng: this.rng,
    };

    // assisted pass options for the human carrier (drives the rings)
    this.handTargetId = -1;
    this.kickTargetId = -1;
    if (carrier && carrier.team === this.humanTeam && carrier.id === this.controlledId) {
      this.computeTargets(carrier, human);
    }

    // ---------------------------------------------------------- players
    for (const p of s.players) {
      if (p.onBench) continue;
      let intent: AiIntent | HumanIntent;
      if (p.id === this.controlledId) {
        const assisted = { ...human };
        this.applyMagnetism(p, assisted, b);
        intent = humanToIntents(assisted, this.kickCharge);
      } else {
        intent = aiIntentFor(p, ctx);
      }
      this.movePlayer(p, intent, dt);

      if (p.id !== this.controlledId) {
        this.tryAiActions(p, intent, ctx);
      }
    }

    this.separatePlayers();

    // ------------------------------------------------------------- ball
    if (b.mode === 'held' && carrier) {
      const fwd = carrier.facing;
      b.x = carrier.x + Math.cos(fwd) * 0.55;
      b.z = carrier.z + Math.sin(fwd) * 0.55;
      b.y = 1.05;
      b.vx = carrier.vx;
      b.vz = carrier.vz;
      b.vy = 0;
      // running with the ball: track metres and auto-bounce
      const moved = Math.hypot(carrier.vx, carrier.vz) * dt;
      this.runSinceBounce += moved;
      if (this.runSinceBounce > 0.01) this.engine.onRunMetres(carrier.id, moved);
      if (this.runSinceBounce > 11.2 || (human.bounce && carrier.id === this.controlledId)) {
        this.runSinceBounce = 0;
        this.engine.onBounce(carrier.id);
        b.y = 0.3;
      }
    } else if (b.mode === 'loose') {
      const before = { x: b.x, z: b.z };
      const res = stepBall(b, dt, this.rng);
      this.engine.onBallFlight(dt);
      if (res.bounced) this.engine.onBallBounced();

      if (res.postHit) {
        const side = b.x > 0 ? 1 : -1;
        this.engine.onGoalLineCrossed(side * FIELD.goalLineX, b.z, {
          postHit: res.postHit,
        });
      } else if (res.crossedGoalLine) {
        this.handleGoalLine(res.goalLineSide, before);
      } else if (res.crossedBoundary) {
        this.handleBoundary(before, b);
      } else {
        this.tryPickupOrCatch();
      }
    }

    // ---------------------------------------------------------- tackles
    if (b.mode === 'held' && carrier) {
      this.tryTackles(carrier, dt, human);
    }

    // ------------------------------------------------- human disposals
    if (carrier && carrier.id === this.controlledId) {
      this.humanActions(carrier, human);
    }

    // charging
    if (human.kickHeld) {
      this.kickCharge = Math.min(1, this.kickCharge + dt * 1.35);
    }

    const drained = this.engine.drainEvents();
    this.eventsOut.push(...drained);
    return this.eventsOut;
  }

  // ------------------------------------------------------------ movement

  private movePlayer(p: PlayerState, intent: AiIntent | HumanIntent, dt: number): void {
    const stats = p.stats;
    const fatigue = 0.82 + 0.18 * p.stamina;
    const sprint = 'sprint' in intent ? intent.sprint : false;
    // sprint build-up: ramps over ~0.7 s instead of snapping on
    const ramping = sprint && mag2(intent) > 0.05;
    p.sprintRamp = Math.max(0, Math.min(1, p.sprintRamp + (ramping ? dt * 1.45 : -dt * 2.1)));
    const sprintMult = sprint ? 1 + 0.17 * p.sprintRamp : 1;
    const maxSpeed = (6.2 + stats.speed * 2.4) * fatigue * sprintMult * this.speedScale();
    let mx = intent.moveX;
    let mz = intent.moveZ;
    const mag = Math.hypot(mx, mz);
    if (mag > 1) {
      mx /= mag;
      mz /= mag;
    }
    const tvx = mx * maxSpeed;
    const tvz = mz * maxSpeed;
    // reversals brake harder — plant and turn
    let accel = mag > 0.05 ? 13 : 11;
    if (mag > 0.05) {
      const sp0 = Math.hypot(p.vx, p.vz);
      if (sp0 > 2.5 && (p.vx * mx + p.vz * mz) / sp0 < -0.35) accel = 17.5;
    }
    p.vx += (tvx - p.vx) * Math.min(1, accel * dt);
    p.vz += (tvz - p.vz) * Math.min(1, accel * dt);
    p.x += p.vx * dt;
    p.z += p.vz * dt;

    // keep everyone on the field
    if (isOutOfBounds(p.x, p.z, 0.35)) {
      const spot = clampInside(p.x, p.z, 2.5);
      p.x = spot.x;
      p.z = spot.z;
      p.vx *= 0.4;
      p.vz *= 0.4;
    }

    // face movement or the ball — turn rate falls with speed
    const speed = Math.hypot(p.vx, p.vz);
    if (speed > 0.6) {
      const target = Math.atan2(p.vz, p.vx);
      let d = target - p.facing;
      while (d > Math.PI) d -= Math.PI * 2;
      while (d < -Math.PI) d += Math.PI * 2;
      const turnRate = 4.6 + 6.6 * (1 - Math.min(1, speed / 9.5));
      p.facing += d * Math.min(1, turnRate * dt);
    }

    p.distanceRun += speed * dt;
    if (p.tackleCooldown > 0) p.tackleCooldown = Math.max(0, p.tackleCooldown - dt);
    p.stamina = Math.max(0.35, p.stamina - speed * dt * 0.0022);
    p.y = 0;
  }

  private speedScale(): number {
    return this.difficulty === 'rookie' ? 0.94 : this.difficulty === 'club' ? 0.99 : 1;
  }

  private separatePlayers(): void {
    const ps = this.engine.state.players.filter((p) => !p.onBench);
    for (let i = 0; i < ps.length; i++) {
      for (let j = i + 1; j < ps.length; j++) {
        const a = ps[i];
        const c = ps[j];
        const dx = c.x - a.x;
        const dz = c.z - a.z;
        const d = Math.hypot(dx, dz);
        if (d > 0.001 && d < SEPARATION_RADIUS * 2) {
          const push = (SEPARATION_RADIUS * 2 - d) * 0.4;
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

  private tryPickupOrCatch(): void {
    const s = this.engine.state;
    const b = s.ball;
    if (b.mode !== 'loose') return;
    // A ball can only be gathered when it is low and slow (ground pickup) or
    // overhead in a catchable window (mark). A kicked ball flies out untouched.
    const ballSpeed = Math.hypot(b.vx, b.vz);
    const groundPickup = b.y < 1.25 && ballSpeed < 9;
    const markCatch = b.y >= 1.8 && b.y < 2.65;
    if (!groundPickup && !markCatch) return;
    const candidates = s.players.filter(
      (p) =>
        !p.onBench &&
        !(p.id === this.kickGraceId && this.kickGraceT > 0) &&
        Math.hypot(p.x - b.x, p.z - b.z) < CATCH_RADIUS &&
        b.y < 2.65
    );
    if (candidates.length === 0) return;

    // contest winner: closest to the ball, weighted by marking skill & jump
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

  private tryTackles(carrier: PlayerState, dt: number, human: HumanIntent): void {
    const s = this.engine.state;
    const RESTART_PHASES = new Set(['kickIn', 'centreBallUp', 'ballUp', 'throwIn', 'freeKick']);
    let nearestAi: PlayerState | null = null;
    let nearestAiDist = Infinity;

    for (const p of s.players) {
      if (p.onBench || p.team === carrier.team || p.id === carrier.id) continue;
      const d = Math.hypot(p.x - carrier.x, p.z - carrier.z);
      // AI opponents get considered out to their commit range; the separation
      // force holds bodies at ~1.7 m, so the old 1.55 m cutoff was unreachable.
      if (d > CPU_TACKLE_RANGE) continue;
      if (p.tackleCooldown > 0) continue;

      if (p.id === this.controlledId) {
        // human tackle: only on the button — walking into a man isn't one
        if (human.tackle && d <= HUMAN_TACKLE_RADIUS) {
          p.tackleCooldown = 0.6;
          this.commitTackle(p, carrier);
          return;
        }
        continue;
      }
      if (d < nearestAiDist) {
        nearestAiDist = d;
        nearestAi = p;
      }
    }

    // CPU tackle: must stay inside the range for a short commit window before
    // the pounce, like Gaelic_Football_3d — not a per-frame dice roll.
    if (nearestAi && nearestAiDist <= CPU_TACKLE_RANGE && !RESTART_PHASES.has(s.phase)) {
      this.cpuTackleTimer += dt;
      if (this.cpuTackleTimer >= CPU_TACKLE_COMMIT_TIME) {
        this.cpuTackleTimer = 0;
        nearestAi.tackleCooldown = CPU_TACKLE_COOLDOWN;
        // difficulty tunes how clean the attempt is once committed
        const foulChance = this.difficulty === 'afl' ? 0.12 : this.difficulty === 'club' ? 0.16 : 0.22;
        const missChance = this.difficulty === 'afl' ? 0.30 : this.difficulty === 'club' ? 0.42 : 0.55;
        const roll = this.rng();
        if (roll < missChance) return; // committed but brought down nothing — the carrier slips clear
        this.commitTackle(nearestAi, carrier, roll < missChance + foulChance);
      }
    } else {
      this.cpuTackleTimer = 0;
    }
  }

  private commitTackle(tackler: PlayerState, carrier: PlayerState, forceFoul = false): void {
    const behind =
      (carrier.x - tackler.x) * Math.cos(carrier.facing) + (carrier.z - tackler.z) * Math.sin(carrier.facing) > 0.6;
    const ctx = {
      priorOpportunity: false,
      highContact: this.rng() < 0.035,
      backContact: forceFoul || (behind && this.rng() < 0.12),
      incorrectDisposal: this.rng() < 0.02,
      attemptedDisposal: false,
      ballSpilledFree: false,
    };
    this.engine.onTackle(tackler.id, carrier.id, ctx);
  }

  private handleGoalLine(side: 1 | -1, before: { x: number; z: number }): void {
    const s = this.engine.state;
    const b = s.ball;
    const crossX = side * FIELD.goalLineX;
    // interpolate z at the crossing
    const t = (crossX - before.x) / (b.x - before.x || 1);
    const crossZ = before.z + (b.z - before.z) * Math.max(0, Math.min(1, t));

    const at = crossX > 0 ? 0 : 1; // team attacking this end
    const defending: TeamId = at === 0 ? 1 : 0;
    const lastTouchTeam = this.lastTouchTeam();
    const deliberateRush =
      lastTouchTeam === defending &&
      (b.lastDisposal === 'handball' || b.lastDisposal === 'none');

    this.engine.onGoalLineCrossed(crossX, crossZ, { deliberateRush });
  }

  private handleBoundary(before: { x: number; z: number }, b: BallState): void {
    const lastTouchTeam = this.lastTouchTeam();
    // "insufficient intent": a ball deliberately forced out by hand/carried
    const deliberate =
      b.lastDisposal === 'none' &&
      lastTouchTeam !== null &&
      this.rng() < 0.25;
    this.engine.onBoundaryCrossed(before.x, before.z, { x: b.x, z: b.z }, false, deliberate);
  }

  private lastTouchTeam(): TeamId | null {
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

  private humanActions(carrier: PlayerState, human: HumanIntent): void {
    const s = this.engine.state;
    const b = s.ball;
    if (human.handball || human.kickReleased) {
      this.kickGraceId = carrier.id;
      this.kickGraceT = 0.85;
    }

    if (human.handball) {
      let dirX = Math.cos(carrier.facing);
      let dirZ = Math.sin(carrier.facing);
      let power = 0.55;
      const target = this.handTargetId >= 0
        ? s.players.find((p) => p.id === this.handTargetId) ?? null
        : null;
      if (target) {
        const dist = Math.hypot(target.x - carrier.x, target.z - carrier.z);
        // strike it where he will be, not where he stands
        const flightT = dist / 15.5;
        const lx = target.x + target.vx * flightT * 0.9;
        const lz = target.z + target.vz * flightT * 0.9;
        const dd = Math.hypot(lx - carrier.x, lz - carrier.z) || 1;
        dirX = (lx - carrier.x) / dd;
        dirZ = (lz - carrier.z) / dd;
        power = Math.min(0.72, Math.max(0.5, 0.5 + (dist - 8) / 70));
      }
      this.engine.onKick(carrier.id, { handball: true });
      launchHandball(b, carrier.x + dirX * 0.5, 1.1, carrier.z + dirZ * 0.5, dirX, dirZ, power, this.rng);
      this.runSinceBounce = 0;
      return;
    }

    if (human.kickReleased) {
      const power = 0.25 + this.kickCharge * 0.75;
      this.kickCharge = 0;
      const setShot = s.phase === 'freeKick' && s.freeKick?.isSetShot;
      let dirX = Math.cos(carrier.facing);
      let dirZ = Math.sin(carrier.facing);
      if (setShot) {
        const goalX = attackGoalX(carrier.team);
        const dx = goalX - carrier.x;
        const dz = -carrier.z;
        const d = Math.hypot(dx, dz) || 1;
        dirX = dx / d;
        dirZ = dz / d;
        // human aim offset bends the shot
        dirZ += human.aimZ * 0.12;
        const dist = Math.hypot(goalX - carrier.x, carrier.z);
        const p2 = Math.min(1, 0.5 + dist / 95 + this.kickCharge * 0.1);
        this.engine.onKick(carrier.id);
        const acc = carrier.stats.kicking * 0.9 + 0.1 - Math.min(0.35, dist / 160);
        launchKick(b, carrier.x + dirX * 0.5, 1.15, carrier.z + dirZ * 0.5, dirX, dirZ, p2, acc, this.rng);
        this.runSinceBounce = 0;
        return;
      }
      const target = this.kickTargetId >= 0
        ? s.players.find((p) => p.id === this.kickTargetId) ?? null
        : null;
      let finalPower = power;
      let acc = carrier.stats.kicking * 0.82 + 0.16;
      if (target) {
        // power fitted to the lead point; your charge still adds 18%
        const flightLoft = 0.34;
        const flightT = (8 + power * 52) / (Math.cos(flightLoft) * Math.sqrt(((8 + power * 52) * 9.81) / Math.sin(2 * flightLoft)) * 1.15);
        const lx = target.x + target.vx * flightT * 0.85;
        const lz = target.z + target.vz * flightT * 0.85;
        const dd = Math.hypot(lx - carrier.x, lz - carrier.z) || 1;
        dirX = (lx - carrier.x) / dd;
        dirZ = (lz - carrier.z) / dd;
        finalPower = Math.min(1, Math.max(0.15, (dd - 8) / 52) * (1 + this.kickCharge * 0.18));
        acc += 0.1; // the assist discount: pointed kicks are cleaner
      }
      this.engine.onKick(carrier.id);
      launchKick(b, carrier.x + dirX * 0.5, 1.15, carrier.z + dirZ * 0.5, dirX, dirZ, finalPower, acc, this.rng);
      this.runSinceBounce = 0;
    }
  }

  /**
   * Gaelic-style pass assist: pick the teammate the stick (or facing) points at,
   * best-scored by angle, spacing and distance. Deterministic.
   */
  private computeTargets(carrier: PlayerState, human: HumanIntent): void {
    let dx = human.moveX;
    let dz = human.moveZ;
    const mag = Math.hypot(dx, dz);
    if (mag > 0.15) {
      dx /= mag;
      dz /= mag;
    } else {
      dx = Math.cos(carrier.facing);
      dz = Math.sin(carrier.facing);
    }
    this.kickTargetId = this.bestPassOption(carrier, dx, dz, 58, Math.PI * 0.42)?.id ?? -1;
    this.handTargetId = this.bestPassOption(carrier, dx, dz, 24, Math.PI * 0.55)?.id ?? -1;
  }

  private bestPassOption(
    carrier: PlayerState,
    dx: number,
    dz: number,
    maxRange: number,
    maxAngle: number
  ): PlayerState | null {
    const s = this.engine.state;
    let best: PlayerState | null = null;
    let bestScore = -Infinity;
    for (const q of s.players) {
      if (q.team !== carrier.team || q.id === carrier.id || q.onBench) continue;
      const rx = q.x - carrier.x;
      const rz = q.z - carrier.z;
      const dist = Math.hypot(rx, rz);
      if (dist < 2.5 || dist > maxRange) continue;
      const dot = (rx * dx + rz * dz) / dist;
      const ang = Math.acos(Math.max(-1, Math.min(1, dot)));
      if (ang > maxAngle) continue;
      let space = 12;
      for (const o of s.players) {
        if (o.team === carrier.team || o.onBench) continue;
        space = Math.min(space, Math.hypot(o.x - q.x, o.z - q.z));
      }
      const score =
        (1 - ang / maxAngle) * 2.4 +
        Math.min(space, 12) * 0.09 +
        dist * 0.012;
      if (score > bestScore) {
        bestScore = score;
        best = q;
      }
    }
    return best;
  }

  /**
   * Pickup magnetism: with the stick idle (or aimed at the ball) the carrier-to-be
   * bends toward a loose ball within 7 m; a high ball sends him to the drop point.
   */
  private applyMagnetism(p: PlayerState, h: HumanIntent, b: BallState): void {
    if (b.mode !== 'loose') return;
    const dx = b.x - p.x;
    const dz = b.z - p.z;

    // high ball — run onto the drop point regardless of the small stick inputs
    if (b.y > 1.6 && b.y < 6) {
      const drop = predictDrop(b);
      const ddx = drop.x - p.x;
      const ddz = drop.z - p.z;
      const dd = Math.hypot(ddx, ddz);
      const stickMag = Math.hypot(h.moveX, h.moveZ);
      const aligned = dx * h.moveX + dz * h.moveZ > 0;
      if (dd > 1.2 && (stickMag < 0.25 || aligned)) {
        const w = stickMag < 0.25 ? 1 : 0.6;
        h.moveX = h.moveX * (1 - w) + (ddx / (dd || 1)) * w;
        h.moveZ = h.moveZ * (1 - w) + (ddz / (dd || 1)) * w;
        if (dd > 12) h.sprint = true;
      }
      return;
    }

    // ground ball within reach
    const dist = Math.hypot(dx, dz);
    if (dist > 7 || dist < 0.05) return;
    const nx = dx / dist;
    const nz = dz / dist;
    const stickMag = Math.hypot(h.moveX, h.moveZ);
    if (stickMag < 0.25) {
      h.moveX = nx;
      h.moveZ = nz;
      if (dist > 3) h.sprint = true;
    } else if (nx * h.moveX + nz * h.moveZ > 0.35) {
      h.moveX = h.moveX * 0.45 + nx * 0.55;
      h.moveZ = h.moveZ * 0.45 + nz * 0.55;
    }
  }

  private tryAiActions(p: PlayerState, intent: AiIntent, ctx: AiContext): void {
    const s = this.engine.state;
    const b = s.ball;
    const isCarrier = b.mode === 'held' && b.holderId === p.id;
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
    if (intent.wantKick && (this.liveTime > 0.45 || s.phase === 'kickIn' || (s.phase === 'freeKick' && s.freeKick?.isSetShot))) {
      const setShot = s.phase === 'freeKick' && s.freeKick?.isSetShot;
      const goalX = attackGoalX(p.team);
      const dist = setShot ? Math.hypot(goalX - p.x, p.z) : 40;
      const acc = p.stats.kicking * (this.difficulty === 'afl' ? 0.9 : this.difficulty === 'club' ? 0.8 : 0.68);
      const power = setShot ? Math.min(1, 0.55 + dist / 95) : intent.power;
      this.engine.onKick(p.id);
      launchKick(b, p.x, 1.15, p.z, intent.aimX, intent.aimZ, power, acc, this.rng);
      this.runSinceBounce = 0;
    }
    void ctx;
  }

  /** Extra event stream for camera/audio (goal celebrations etc). */
  recentEvents(): MatchEvent[] {
    return this.eventsOut;
  }

  controlled(): PlayerState | null {
    return this.engine.state.players.find((p) => p.id === this.controlledId) ?? null;
  }
}

function humanToIntents(h: HumanIntent, charge: number): AiIntent {
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
    power: 0.25 + charge * 0.75,
  };
}

export { emptyIntent, defendGoalX };
