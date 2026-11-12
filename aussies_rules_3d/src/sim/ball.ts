/** Ball physics for an oval Sherrin-style football. */
import { BallState, FIELD } from '../rules/types';
import { isOutOfBounds } from '../rules/field';

export const BALL_RADIUS = 0.15;
const GRAVITY = 9.81;
const AIR_DRAG = 0.06;
const BOUNCE_RESTITUTION = 0.52;
const GROUND_FRICTION = 0.8;
const ROLL_FRICTION = 1.4; // per-second decay of rolling speed

export interface BallStepResult {
  /** Previous position (for line-crossing detection). */
  prevX: number;
  prevY: number;
  prevZ: number;
  /** Set when the ball hits the ground this step. */
  bounced: boolean;
  /** Set when the ball crosses the boundary line this step. */
  crossedBoundary: boolean;
  /** Set when the ball crosses a goal line this step (x ≈ ±goalLineX). */
  crossedGoalLine: boolean;
  /** Which goal line: +1 east, -1 west. */
  goalLineSide: 1 | -1;
  /** Post collision this step, if any. */
  postHit: 'goalPost' | 'behindPost' | null;
}

export function stepBall(ball: BallState, dt: number, rng: () => number = Math.random): BallStepResult {
  const prevX = ball.x;
  const prevY = ball.y;
  const prevZ = ball.z;

  const res: BallStepResult = {
    prevX, prevY, prevZ,
    bounced: false,
    crossedBoundary: false,
    crossedGoalLine: false,
    goalLineSide: 1,
    postHit: null,
  };

  if (ball.mode === 'held' || ball.mode === 'heldUmpire' || ball.mode === 'dead') {
    return res;
  }

  // aerodynamics: drag opposes velocity, slight magnus from spin
  const speed = Math.hypot(ball.vx, ball.vy, ball.vz);
  const drag = AIR_DRAG * speed;
  if (speed > 0.001) {
    ball.vx -= (ball.vx / speed) * drag * dt;
    ball.vy -= (ball.vy / speed) * drag * dt;
    ball.vz -= (ball.vz / speed) * drag * dt;
  }
  // spin curves the ball in flight (drop punt swings)
  ball.vz += ball.spin * dt * 1.4;
  ball.spin *= 1 - 0.35 * dt;

  ball.vy -= GRAVITY * dt;
  ball.x += ball.vx * dt;
  ball.y += ball.vy * dt;
  ball.z += ball.vz * dt;

  // ground bounce
  if (ball.y <= BALL_RADIUS && ball.vy < 0) {
    ball.y = BALL_RADIUS;
    ball.vy = -ball.vy * BOUNCE_RESTITUTION * (0.85 + rng() * 0.3);
    ball.vx *= GROUND_FRICTION;
    ball.vz *= GROUND_FRICTION;
    ball.spin *= 0.6;
    if (Math.abs(ball.vy) < 0.6) ball.vy = 0;
    res.bounced = true;
  } else if (ball.y <= BALL_RADIUS + 0.02 && Math.abs(ball.vy) < 0.3) {
    // rolling on the ground: apply rolling friction
    const f = Math.max(0, 1 - ROLL_FRICTION * dt);
    ball.vx *= f;
    ball.vz *= f;
    ball.y = BALL_RADIUS;
    ball.vy = 0;
  }

  // post collisions (padded posts sit on the goal line)
  const nearGoalLine = Math.abs(Math.abs(ball.x) - FIELD.goalLineX) < 0.35;
  if (nearGoalLine && ball.y < 10) {
    const az = Math.abs(ball.z);
    const dGoal = Math.abs(az - FIELD.goalPostHalf);
    const dBehind = Math.abs(az - FIELD.behindPostHalf);
    if (dGoal < 0.45 && ball.y < 9.6) {
      res.postHit = 'goalPost';
      ball.vx = -ball.vx * 0.4;
      ball.vz += (ball.z > 0 ? 1 : -1) * 2.5;
    } else if (dBehind < 0.45 && ball.y < 6.0) {
      res.postHit = 'behindPost';
      ball.vx = -ball.vx * 0.4;
      ball.vz += (ball.z > 0 ? 1 : -1) * 2.5;
    }
  }

  // goal line crossing (between the behind posts)
  const goalLineX = FIELD.goalLineX;
  if (prevX < goalLineX && ball.x >= goalLineX && Math.abs(ball.z) <= FIELD.behindPostHalf + 0.2) {
    res.crossedGoalLine = true;
    res.goalLineSide = 1;
  } else if (prevX > -goalLineX && ball.x <= -goalLineX && Math.abs(ball.z) <= FIELD.behindPostHalf + 0.2) {
    res.crossedGoalLine = true;
    res.goalLineSide = -1;
  }

  // boundary crossing
  if (!res.crossedGoalLine && isOutOfBounds(ball.x, ball.z, BALL_RADIUS)) {
    res.crossedBoundary = true;
  }

  return res;
}

/** Launch a kicked ball from a position toward a target with power 0..1. */
export function launchKick(
  ball: BallState,
  fromX: number,
  fromY: number,
  fromZ: number,
  dirX: number,
  dirZ: number,
  power: number,
  accuracy: number,
  rng: () => number
): void {
  const dist = 8 + power * 52; // 8..60 metres target
  const noise = (1 - accuracy) * 0.16;
  const ang = Math.atan2(dirZ, dirX) + (rng() - 0.5) * noise * 2;
  const loft = 0.22 + power * 0.32 + (rng() - 0.5) * noise;
  // projectile range solve v = sqrt(g·R / sin(2θ)), with 15% headroom for drag
  const speed = Math.sqrt((dist * GRAVITY) / Math.max(0.35, Math.sin(2 * loft))) * 1.15;
  ball.mode = 'loose';
  ball.holderId = null;
  ball.x = fromX;
  ball.y = fromY;
  ball.z = fromZ;
  ball.vx = Math.cos(ang) * speed * Math.cos(loft);
  ball.vz = Math.sin(ang) * speed * Math.cos(loft);
  ball.vy = speed * Math.sin(loft);
  ball.spin = (rng() - 0.5) * 1.2;
}

/** Handball: lower, shorter, faster release. */
export function launchHandball(
  ball: BallState,
  fromX: number,
  fromY: number,
  fromZ: number,
  dirX: number,
  dirZ: number,
  power: number,
  rng: () => number
): void {
  const dist = 4 + power * 16;
  const speed = 7 + power * 15;
  const ang = Math.atan2(dirZ, dirX) + (rng() - 0.5) * 0.12;
  ball.mode = 'loose';
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

/** Predict where a loose ball will land (y ≈ 1.5 m hand-catch height). */
export function predictDrop(ball: BallState): { x: number; z: number; t: number } {
  const y0 = ball.y;
  const target = 1.5;
  // 0.5 g t^2 - vy t + (y0 - target) = 0  → take the positive root
  const disc = ball.vy * ball.vy + 2 * GRAVITY * (y0 - target);
  const t = disc >= 0 ? (ball.vy + Math.sqrt(disc)) / GRAVITY : 0.6;
  // rough drag compensation so long kicks don't overshoot wildly
  const dragK = 1 - Math.min(0.18, AIR_DRAG * t);
  return { x: ball.x + ball.vx * t * dragK, z: ball.z + ball.vz * t * dragK, t: Math.max(0.05, t) };
}
