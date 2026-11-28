/**
 * Planted-foot / two-bone leg IK — pure math port of the Gaelic branch's
 * `strideLimit()` + foot-plant fade + 2-bone solve (Gaelic_Football_3d/src/main.c
 * `plantOne`/`stretchLeg`, constants GA_LEG_MAX_STRIDE_SCALE / GA_LEG_MAX_REACH).
 *
 * NOT WIRED YET into the three.js render path. Writing the solved pose back
 * into the skinned rig (parent-space bone writes or a pose-override pass) is
 * deliberate future work behind a GPU-verified flag — see docs/MOTION_IK.md.
 * This module is pure, deterministic and unit-tested so that wiring is a
 * mechanical integration step, not a redesign.
 *
 * Conventions: "model space" means metres relative to the character root,
 * +y up, model forward +z (matches the squad GLB's rest pose and the Gaelic
 * solver). Yaw is three.js rotation.y. The root is assumed to have zero
 * pitch/roll (as in this game).
 */
import * as THREE from 'three';

export const MAX_STRIDE_SCALE = 1.55; // GA_LEG_MAX_STRIDE_SCALE
export const MAX_REACH_FACTOR = 0.95; // GA_LEG_MAX_REACH
export const PLANT_LIFT_LIMIT = 0.2; // m — foot above this is airborne, plant releases
export const PLANT_GROUND_LIMIT = 0.11; // m — foot at/below this may be planted
export const PLANT_ATTACK = 0.07; // am_smooth response time (s) planting
export const PLANT_RELEASE = 0.09; // am_smooth response time (s) releasing
export const PLANT_WEIGHT_START = 0.02; // below this plant may engage
export const PLANT_WEIGHT_DEAD = 0.001; // below this plant fully releases

/** Stride scale cap: 1.0 at ≤1 m/s rising linearly to MAX_STRIDE_SCALE at 7 m/s. */
export function strideLimit(speed: number): number {
  if (!Number.isFinite(speed)) return 1.0;
  const t = Math.min(1, Math.max(0, (speed - 1.0) / 6.0));
  return 1.0 + (MAX_STRIDE_SCALE - 1.0) * t;
}

/** Exact port of `am_smooth(current, target, dt, response)`: exponential approach. */
export function smoothToward(current: number, target: number, dt: number, response: number): number {
  if (!Number.isFinite(current) || !Number.isFinite(target) || !Number.isFinite(dt) || dt < 0 ||
      !Number.isFinite(response) || response <= 0) {
    return current;
  }
  const blend = -Math.expm1(-dt / response);
  return current + (target - current) * blend;
}

export interface PlantSide {
  /** Plant is actively holding this foot. */
  on: boolean;
  /** World-space anchor point of the planted foot (y ignored). */
  x: number;
  z: number;
  /** Smoothed 0..1 blend toward the planted pose (am_smooth). */
  weight: number;
}

export const createPlantSide = (): PlantSide => ({ on: false, x: 0, z: 0, weight: 0 });

/**
 * Mirror of Gaelic `plantOne` state machine (foot lift gates + am_smooth fade).
 * All positions are WORLD space: `footLift` is the foot's world height above
 * the ground plane and `footWorld` the foot's world position (y ignored when
 * anchoring). AR3D's sim runs on a flat pitch, so world y == height.
 */
export function updatePlantSide(
  side: PlantSide,
  dt: number,
  footLift: number,
  footWorld: THREE.Vector3,
): void {
  if (footLift > PLANT_LIFT_LIMIT) side.on = false;
  if (!side.on && side.weight < PLANT_WEIGHT_START && footLift <= PLANT_GROUND_LIMIT) {
    side.x = footWorld.x;
    side.z = footWorld.z;
    side.on = true;
  }
  if (!side.on && side.weight < PLANT_WEIGHT_DEAD) {
    side.weight = 0;
    return;
  }
  side.weight = smoothToward(side.weight, side.on ? 1 : 0, dt, side.on ? PLANT_ATTACK : PLANT_RELEASE);
}

export const DEFAULT_FORWARD = new THREE.Vector3(0, 0, 1);

/**
 * Knee pole preference (port of Gaelic `legPole`): preserve the current knee
 * direction when it is forward of the hip→target line; otherwise fall back to
 * `forward` projected ⊥ hip→target (model-forward in Gaelic, facing in AR3D).
 */
export function legPole(
  hip: THREE.Vector3,
  knee: THREE.Vector3,
  target: THREE.Vector3,
  out: THREE.Vector3,
  forward: THREE.Vector3 = DEFAULT_FORWARD,
): THREE.Vector3 {
  const d = out.copy(target).sub(hip);
  const length = d.length();
  const pole = new THREE.Vector3().copy(knee).sub(hip);
  if (length < 1e-4) return pole;
  d.normalize();
  pole.addScaledVector(d, -pole.dot(d));
  const fwdDot = pole.dot(forward);
  if (pole.length() < 1e-4 || fwdDot < 0) {
    // Knee kicked backward/degenerate → use `forward` projected ⊥ hip→target.
    const projected = forward.clone().addScaledVector(d, -forward.dot(d));
    if (projected.length() >= 1e-4) pole.copy(projected);
  }
  return pole;
}

export interface LegLengths {
  l1: number;
  l2: number;
}

export const legLengths = (hip: THREE.Vector3, calf: THREE.Vector3, foot: THREE.Vector3): LegLengths => ({
  l1: hip.distanceTo(calf),
  l2: calf.distanceTo(foot),
});

/**
 * Two-bone IK: given hip fixed and a desired foot target, solve calf & foot
 * positions in place. Knee direction follows `legPole` (model-forward pole).
 * Target is clamped to (L1+L2)*MAX_REACH_FACTOR of hip; degenerate inputs are
 * returned unchanged rather than producing NaNs.
 */
export function solveTwoBoneIK(
  hip: THREE.Vector3,
  calf: THREE.Vector3,
  foot: THREE.Vector3,
  target: THREE.Vector3,
  forward: THREE.Vector3 = DEFAULT_FORWARD,
): void {
  const { l1, l2 } = legLengths(hip, calf, foot);
  if (l1 < 0.05 || l2 < 0.05) return;

  const reach = (l1 + l2) * MAX_REACH_FACTOR;
  const dir = new THREE.Vector3().copy(target).sub(hip);
  let dist = dir.length();
  if (dist < 1e-5) {
    dir.copy(DEFAULT_FORWARD);
    dist = 1e-5;
  }
  const clampedDist = Math.min(Math.max(dist, Math.abs(l1 - l2) * 1.001 + 1e-4), reach);
  const clamped = clampedDist < dist ? dir.normalize().multiplyScalar(clampedDist) : dir.clone();
  const outTarget = new THREE.Vector3().copy(hip).add(clamped);

  const n = clamped.clone().normalize();
  const cosA = (l1 * l1 + clampedDist * clampedDist - l2 * l2) / (2 * l1 * clampedDist);
  const d = l1 * Math.min(1, Math.max(-1, cosA));
  const h = Math.sqrt(Math.max(0, l1 * l1 - d * d));
  const pole = legPole(hip, calf, outTarget, new THREE.Vector3(), forward);
  if (pole.lengthSq() < 1e-10) pole.copy(DEFAULT_FORWARD);
  pole.normalize();

  calf.copy(hip).addScaledVector(n, d).addScaledVector(pole, h);
  foot.copy(outTarget);
}
