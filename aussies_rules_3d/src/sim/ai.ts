/**
 * Team AI — positioning shapes, leads, pressure and ball use.
 *
 * The AI plays proper footy: team shape slides with the ball, forwards lead
 * to space, defenders man up, the carrier kicks to the best option and shoots
 * on goal inside 50. Difficulty scales reaction speed, pressure and accuracy.
 */
import { FIELD, MatchState, PlayerState, TeamId } from '../rules/types';
import { attackGoalX, defendGoalX, insideAttackArc } from '../rules/field';

export type Difficulty = 'rookie' | 'club' | 'afl';

export interface AiIntent {
  moveX: number;
  moveZ: number;
  sprint: boolean;
  wantKick: boolean;
  wantHandball: boolean;
  wantTackle: boolean;
  wantBounce: boolean;
  /** Aim direction for kicks (towards a target). */
  aimX: number;
  aimZ: number;
  /** 0..1 power. */
  power: number;
}

export function emptyIntent(): AiIntent {
  return {
    moveX: 0, moveZ: 0, sprint: false,
    wantKick: false, wantHandball: false, wantTackle: false, wantBounce: false,
    aimX: 1, aimZ: 0, power: 0.6,
  };
}

const DIFF: Record<Difficulty, { reaction: number; accuracy: number; pressure: number; speed: number }> = {
  rookie: { reaction: 0.55, accuracy: 0.72, pressure: 0.5, speed: 0.93 },
  club: { reaction: 0.78, accuracy: 0.84, pressure: 0.8, speed: 0.98 },
  afl: { reaction: 0.95, accuracy: 0.92, pressure: 1.0, speed: 1.0 },
};

/** Role home positions as fractions of (goal-to-goal, wing) space, per team. */
const ROLE_SHAPE: Record<string, { fx: number; fz: number }> = {
  fullback: { fx: -0.38, fz: 0.0 },
  keyDefender: { fx: -0.30, fz: 0.18 },
  halfBack: { fx: -0.16, fz: 0.30 },
  midfielder: { fx: 0.0, fz: 0.22 },
  ruck: { fx: 0.02, fz: 0.0 },
  halfForward: { fx: 0.16, fz: 0.30 },
  keyForward: { fx: 0.30, fz: 0.18 },
  fullForward: { fx: 0.38, fz: 0.0 },
};

export function homePosition(
  p: PlayerState,
  ballX: number,
  ballZ: number,
  phase: string
): { x: number; z: number } {
  const dir = p.team === 0 ? 1 : -1; // team 0 attacks +x
  const shape = ROLE_SHAPE[p.role] ?? ROLE_SHAPE.midfielder;

  // formation anchored on the ball, sliding toward the defended goal
  const anchorX = ballX * 0.55;
  const anchorZ = ballZ * 0.45;
  let x = anchorX + dir * shape.fx * 72;
  let z = anchorZ + shape.fz * 52 * (p.id % 2 === 0 ? 1 : -1);

  // hold the 6-6-6 shape at centre ball-ups
  if (phase === 'centreBallUp') {
  const gx = attackGoalX(p.team);
  const dg = defendGoalX(p.team);
  if (shape.fx > 0.1) {
    x = gx - dir * (28 + shape.fx * 20);
  } else if (shape.fx < -0.1) {
    x = dg + dir * (28 + -shape.fx * 20);
  } else {
    x = dir * 14;
  }
    z = shape.fz * 60 * (p.number % 2 === 0 ? 1 : -1) + (p.number % 5) * 4 - 8;
  }

  return {
    x: Math.max(-FIELD.boundaryA + 6, Math.min(FIELD.boundaryA - 6, x)),
    z: Math.max(-FIELD.boundaryB + 6, Math.min(FIELD.boundaryB - 6, z)),
  };
}

export interface AiContext {
  state: MatchState;
  difficulty: Difficulty;
  /** Team currently possessing (or null). */
  possessingTeam: TeamId | null;
  carrierId: number | null;
  /** Seconds since the ball became live at the current stoppage. */
  liveTime: number;
  /** Seeded RNG for deterministic sims. */
  rng: () => number;
}

/** Decide what one AI player does this frame. */
export function aiIntentFor(p: PlayerState, ctx: AiContext): AiIntent {
  const intent = emptyIntent();
  const s = ctx.state;
  const b = s.ball;
  const diff = DIFF[ctx.difficulty];
  const dir = p.team === 0 ? 1 : -1;

  if (p.onBench) return intent;

  const toBallX = b.x - p.x;
  const toBallZ = b.z - p.z;
  const distBall = Math.hypot(toBallX, toBallZ);

  // ------------------------------------------------------------- carrier
  if (ctx.carrierId === p.id && b.mode === 'held') {
    const goalX = attackGoalX(p.team);
    const distGoal = Math.hypot(goalX - p.x, 0 - p.z);
    const pressured = isPressured(p, ctx);

    if (s.phase === 'kickIn') {
      // kick-in: clear the square, preferably long to a flank
      intent.wantKick = true;
      intent.power = 0.75;
      const target = bestKickTarget(p, ctx) ?? { x: dir * 30, z: (p.number % 2 ? 1 : -1) * 40 };
      aim(intent, p, target.x, target.z);
      return intent;
    }

    if (insideAttackArc(p.x, p.z, p.team) && distGoal < 52) {
      // shot for goal
      intent.wantKick = true;
      intent.power = Math.min(1, 0.55 + distGoal / 70);
      const spread = (1 - diff.accuracy) * (distGoal / 60);
      const z = (ctx.rng() - 0.5) * spread * 10;
      aim(intent, p, goalX, z);
      return intent;
    }

    if (pressured && ctx.rng() < 0.035 * diff.reaction * 60 * 0.02) {
      // under pressure: handball out or hack it forward
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

    // run with it (auto-bounce handled by the sim)
    const gap = bestRunGap(p, ctx);
    intent.moveX = gap.x;
    intent.moveZ = gap.z;
    intent.sprint = true;
    return intent;
  }

  // --------------------------------------------------------- ball contest
  const loose = b.mode === 'loose';
  // limit the pack: only the three nearest players per team may chase the ball
  const mayChase = teammatesCloserToBall(p, ctx) < 3;
  const chaseThis =
    mayChase &&
    ((loose && distBall < 11) ||
      (ctx.possessingTeam !== null && ctx.possessingTeam !== p.team && distBall < 8) ||
      (ctx.carrierId !== null && isNearestChaser(p, ctx)));

  if (chaseThis) {
    // lead the intercept slightly
    const lead = 0.28 * diff.reaction;
    intent.moveX = normalize(toBallX + b.vx * lead);
    intent.moveZ = normalize(toBallZ + b.vz * lead);
    intent.sprint = distBall > 6;
    if (distBall < 1.6 && ctx.possessingTeam !== null && ctx.possessingTeam !== p.team) {
      intent.wantTackle = true;
    }
    return intent;
  }

  // ------------------------------------------------------------- shape up
  const home = homePosition(p, b.x, b.z, s.phase);
  const hx = home.x - p.x;
  const hz = home.z - p.z;
  const d = Math.hypot(hx, hz);
  if (d > 2.5) {
    intent.moveX = normalize(hx);
    intent.moveZ = normalize(hz);
    intent.sprint = d > 18;
  }

  // forwards lead toward goal when their team has the ball
  if (ctx.possessingTeam === p.team && (p.role === 'keyForward' || p.role === 'fullForward' || p.role === 'halfForward')) {
    const goalX = attackGoalX(p.team);
    intent.moveX = normalize((goalX - p.x) * 0.5 + hx);
    intent.moveZ = normalize(-p.z * 0.6 + hz * 0.4);
    intent.sprint = true;
  }

  // defenders guard the space in front of goal when defending
  if (ctx.possessingTeam !== null && ctx.possessingTeam !== p.team &&
    (p.role === 'fullback' || p.role === 'keyDefender')) {
    const ownGoal = defendGoalX(p.team);
    const dangerX = ownGoal + dir * 18;
    intent.moveX = normalize(dangerX - p.x);
    intent.moveZ = normalize(-p.z * 0.5);
  }

  return intent;
}

/** How many teammates are closer to the ball than this player — caps the pack. */
function teammatesCloserToBall(p: PlayerState, ctx: AiContext): number {
  const b = ctx.state.ball;
  const d = (b.x - p.x) ** 2 + (b.z - p.z) ** 2;
  let n = 0;
  for (const q of ctx.state.players) {
    if (q.team !== p.team || q.id === p.id || q.onBench) continue;
    if ((b.x - q.x) ** 2 + (b.z - q.z) ** 2 < d) n++;
  }
  return n;
}

function isPressured(p: PlayerState, ctx: AiContext): boolean {
  for (const q of ctx.state.players) {
    if (q.team === p.team || q.onBench) continue;
    if (Math.hypot(q.x - p.x, q.z - p.z) < 3.2) return true;
  }
  return false;
}

function isNearestChaser(p: PlayerState, ctx: AiContext): boolean {
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

/** Best forward target to kick to: leads, space and scoring value. */
export function bestKickTarget(
  p: PlayerState,
  ctx: AiContext
): { x: number; z: number; player: PlayerState } | null {
  const dir = p.team === 0 ? 1 : -1;
  const goalX = attackGoalX(p.team);
  let best: { x: number; z: number; player: PlayerState; score: number } | null = null;
  for (const q of ctx.state.players) {
    if (q.team !== p.team || q.id === p.id || q.onBench) continue;
    const dx = q.x - p.x;
    if (dx * dir < -6) continue; // behind the carrier: not an option
    const dist = Math.hypot(dx, q.z - p.z);
    if (dist < 8 || dist > 62) continue;
    // score: closer to goal is better, well spaced from opponents
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

function bestHandballTarget(p: PlayerState, ctx: AiContext): { x: number; z: number } | null {
  let best: { x: number; z: number; d: number } | null = null;
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

/** Run direction that opens the best kicking lane. */
function bestRunGap(p: PlayerState, ctx: AiContext): { x: number; z: number } {
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

function normalize(v: number): number {
  return Math.max(-1, Math.min(1, v));
}

function aim(intent: AiIntent, p: PlayerState, x: number, z: number): void {
  const dx = x - p.x;
  const dz = z - p.z;
  const d = Math.hypot(dx, dz) || 1;
  intent.aimX = dx / d;
  intent.aimZ = dz / d;
}
