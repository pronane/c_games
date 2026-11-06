/** Field geometry for the MCG-scale oval. Pure functions, metres. */
import { FIELD } from './types';

/** Signed "oval radius" at an angle: distance from centre to boundary. */
export function boundaryRadiusAt(angle: number): number {
  const { boundaryA: a, boundaryB: b, shapeN: n } = FIELD;
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  const x = Math.sign(c) * Math.pow(Math.abs(c), 2 / n) * a;
  const y = Math.sign(s) * Math.pow(Math.abs(s), 2 / n) * b;
  return Math.hypot(x, y);
}

/** True when the whole ball is outside the boundary (given as ball radius). */
export function isOutOfBounds(x: number, z: number, ballRadius = 0.15): boolean {
  const { boundaryA: a, boundaryB: b, shapeN: n } = FIELD;
  const v = Math.pow(Math.abs(x) / (a + ballRadius), n) + Math.pow(Math.abs(z) / (b + ballRadius), n);
  return v > 1;
}

/** Distance to the boundary along the outward normal-ish (positive inside). */
export function metresInside(x: number, z: number): number {
  const { boundaryA: a, boundaryB: b, shapeN: n } = FIELD;
  const v = Math.pow(Math.abs(x) / a, n) + Math.pow(Math.abs(z) / b, n);
  // approximate: scale factor to reach the boundary from the origin
  const t = Math.pow(v, 1 / n);
  return (1 - t) * Math.min(a, b);
}

/** Which goal end a team attacks: team 0 attacks +x, team 1 attacks -x. */
export function attackGoalX(team: 0 | 1): number {
  return team === 0 ? FIELD.goalLineX : -FIELD.goalLineX;
}

export function defendGoalX(team: 0 | 1): number {
  return -attackGoalX(team);
}

/** Inside the 50 m arc of the goal a team attacks (or defends). */
export function insideAttackArc(x: number, z: number, team: 0 | 1): boolean {
  const gx = attackGoalX(team);
  return Math.hypot(x - gx, z) <= FIELD.arcRadius;
}

export function insideDefendArc(x: number, z: number, team: 0 | 1): boolean {
  return insideAttackArc(x, z, team === 0 ? 1 : 0);
}

/** Between the two 50 m arcs (the corridor where the 2026 lasso law applies). */
export function betweenArcs(x: number): boolean {
  return Math.abs(x) < FIELD.goalLineX - FIELD.arcRadius;
}

/** Goal line crossing detector. Returns 'goal' | 'behind' | 'post' | null. */
export type ScoreCrossing =
  | { kind: 'goal'; team: 0 | 1 }
  | { kind: 'behind'; team: 0 | 1 }
  | { kind: 'goalPost' }
  | { kind: 'behindPost' }
  | null;

/**
 * Decide what a ball crossing the goal line at (x≈±goalLineX, z) scored.
 * `team` is the team attacking that end.
 */
export function scoreAtCrossing(crossX: number, z: number): ScoreCrossing {
  const side = crossX > 0 ? 0 : 1; // team attacking this goal
  const az = Math.abs(z);
  if (az <= FIELD.goalPostHalf) return { kind: 'goal', team: side };
  if (az <= FIELD.behindPostHalf) return { kind: 'behind', team: side };
  return null;
}

/** Nearest post kind at a crossing point (for post-hit rules). */
export function postHitAt(_x: number, z: number): 'goalPost' | 'behindPost' | null {
  const az = Math.abs(z);
  // post collision checked in physics; helper classifies by |z|
  if (Math.abs(az - FIELD.goalPostHalf) < 0.35) return 'goalPost';
  if (Math.abs(az - FIELD.behindPostHalf) < 0.35) return 'behindPost';
  return null;
}

/** Goal square test: within 9 m of the goal line, between the goal posts. */
export function inGoalSquare(x: number, z: number, defendingTeam: 0 | 1): boolean {
  const gx = defendGoalX(defendingTeam);
  const depth = Math.abs(x - gx);
  return depth <= FIELD.goalSquareDepth && Math.abs(z) <= FIELD.goalPostHalf;
}

export function inCentreSquare(x: number, z: number): boolean {
  return Math.abs(x) <= FIELD.centreSquareHalf && Math.abs(z) <= FIELD.centreSquareHalf;
}

export function inCentreCircle(x: number, z: number): boolean {
  return Math.hypot(x, z) <= FIELD.centreCircleRadius;
}

/** Point where the ball crossed the boundary, extrapolating from two samples. */
export function boundaryCrossing(
  x0: number, z0: number, x1: number, z1: number
): { x: number; z: number } {
  // binary search the segment for the boundary
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

/** Clamp a kick-in / free-kick spot so it is inside the boundary. */
export function clampInside(x: number, z: number, margin = 1.0): { x: number; z: number } {
  if (!isOutOfBounds(x, z, -margin)) return { x, z };
  const ang = Math.atan2(z, x);
  const r = boundaryRadiusAt(ang) - margin;
  return { x: Math.cos(ang) * r, z: Math.sin(ang) * r };
}
