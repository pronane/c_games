import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import {
  MAX_STRIDE_SCALE,
  MAX_REACH_FACTOR,
  PLANT_LIFT_LIMIT,
  PLANT_GROUND_LIMIT,
  strideLimit,
  smoothToward,
  createPlantSide,
  updatePlantSide,
  solveTwoBoneIK,
  legPole,
} from '../src/motion/legIk';

describe('strideLimit', () => {
  it('is 1.0 at and below 1 m/s', () => {
    expect(strideLimit(0)).toBe(1.0);
    expect(strideLimit(1.0)).toBe(1.0);
  });
  it('is monotonic non-decreasing', () => {
    let prev = -Infinity;
    for (let v = 0; v <= 7; v += 0.25) {
      const s = strideLimit(v);
      expect(s).toBeGreaterThanOrEqual(prev);
      prev = s;
    }
  });
  it('hits MAX_STRIDE_SCALE at 7 m/s and clips beyond', () => {
    expect(strideLimit(7)).toBeCloseTo(MAX_STRIDE_SCALE, 6);
    expect(strideLimit(9)).toBe(MAX_STRIDE_SCALE);
    expect(strideLimit(4)).toBeCloseTo(1.275, 6);
  });
  it('tolerates NaN/Infinity', () => {
    expect(strideLimit(NaN)).toBe(1.0);
    expect(strideLimit(-5)).toBe(1.0);
  });
});

describe('smoothToward (am_smooth port)', () => {
  it('moves current toward target without overshoot', () => {
    let v = 0;
    for (let i = 0; i < 600; i++) v = smoothToward(v, 1, 1 / 60, 0.07);
    expect(v).toBeGreaterThan(0.99);
  });
  it('zero dt leaves value unchanged', () => {
    expect(smoothToward(0.4, 1, 0, 0.07)).toBe(0.4);
  });
  it('rejects bad inputs (returns current)', () => {
    expect(smoothToward(0.4, 1, -1, 0.07)).toBe(0.4);
    expect(smoothToward(0.4, 1, 0.1, 0)).toBe(0.4);
    expect(smoothToward(NaN, 1, 0.1, 0.07)).toBeNaN();
  });
});

describe('updatePlantSide state machine', () => {
  it('plants a low foot and holds it while low', () => {
    const side = createPlantSide();
    const foot = new THREE.Vector3(10.2, PLANT_GROUND_LIMIT - 0.01, 20.3);
    updatePlantSide(side, 1 / 60, foot.y, foot);
    expect(side.on).toBe(true);
    for (let i = 0; i < 600; i++) updatePlantSide(side, 1 / 60, foot.y, foot);
    expect(side.weight).toBeGreaterThan(0.99);
  });
  it('releases when the foot lifts above the limit', () => {
    const side = createPlantSide();
    const low = new THREE.Vector3(0, PLANT_GROUND_LIMIT - 0.01, 0.5);
    updatePlantSide(side, 1 / 60, low.y, low);
    for (let i = 0; i < 120; i++) updatePlantSide(side, 1 / 60, low.y, low);
    const high = new THREE.Vector3(0, PLANT_LIFT_LIMIT + 0.05, 0.5);
    updatePlantSide(side, 1 / 60, high.y, high);
    expect(side.on).toBe(false);
    for (let i = 0; i < 600; i++) updatePlantSide(side, 1 / 60, high.y, high);
    expect(side.weight).toBeLessThan(0.01);
  });
  it('does not replant until weight falls below the gate', () => {
    const side = createPlantSide();
    side.weight = 0.5; // still blending out from a previous plant
    const foot = new THREE.Vector3(0, 0, 0.4);
    updatePlantSide(side, 1 / 60, 0.0, foot);
    expect(side.on).toBe(false); // gated by PLANT_WEIGHT_START
  });
  it('stores the world anchor of the planted foot', () => {
    const side = createPlantSide();
    const foot = new THREE.Vector3(5, 0.05, 6);
    updatePlantSide(side, 1 / 60, foot.y, foot);
    expect(side.x).toBeCloseTo(5, 6);
    expect(side.z).toBeCloseTo(6, 6);
  });
});

describe('solveTwoBoneIK', () => {
  const hip = () => new THREE.Vector3(0, 1.0, 0);
  const calf = () => new THREE.Vector3(0, 0.55, 0.05);
  const foot = () => new THREE.Vector3(0, 0.08, 0.1);

  it('preserves segment lengths for a reachable target', () => {
    const h = hip(); const c = calf(); const f = foot();
    const l1 = h.distanceTo(c);
    const l2 = c.distanceTo(f);
    solveTwoBoneIK(h, c, f, new THREE.Vector3(0.15, 0.25, 0.35));
    expect(h.distanceTo(c)).toBeCloseTo(l1, 5);
    expect(c.distanceTo(f)).toBeCloseTo(l2, 5);
  });
  it('clamps an unreachable target to max reach around the hip', () => {
    const h = hip(); const c = calf(); const f = foot();
    const l1 = h.distanceTo(c);
    const l2 = c.distanceTo(f);
    solveTwoBoneIK(h, c, f, new THREE.Vector3(0, 0.5, 30));
    expect(h.distanceTo(f)).toBeLessThanOrEqual((l1 + l2) * MAX_REACH_FACTOR + 1e-5);
    expect(c.distanceTo(f)).toBeCloseTo(l2, 5);
  });
  it('keeps the knee forward of the hip→ankle line (z-pole preference)', () => {
    const h = hip(); const c = calf(); const f = foot();
    solveTwoBoneIK(h, c, f, new THREE.Vector3(0, 0.35, 0.5));
    const hipToFoot = f.clone().sub(h).normalize();
    const hipToKnee = c.clone().sub(h).normalize();
    // knee pole must have positive model-forward (z) component
    expect(c.z).toBeGreaterThan(0);
    // knee bent forward: roughly aligned with hip→ankle axis, not sideways/behind
    expect(hipToKnee.dot(hipToFoot)).toBeGreaterThan(0.8);
  });
  it('handles a straight-leg target at exactly max reach without NaN', () => {
    const h = hip(); const c = calf(); const f = foot();
    const l1 = h.distanceTo(c);
    const l2 = c.distanceTo(f);
    const reach = (l1 + l2) * MAX_REACH_FACTOR;
    solveTwoBoneIK(h, c, f, new THREE.Vector3(0, -1.0, reach));
    for (const v of [c, f]) {
      expect(Number.isFinite(v.x)).toBe(true);
      expect(Number.isFinite(v.y)).toBe(true);
      expect(Number.isFinite(v.z)).toBe(true);
    }
  });
  it('degenerate hip-at-target input does not produce NaN', () => {
    const h = hip(); const c = calf(); const f = foot();
    solveTwoBoneIK(h, c, f, h.clone());
    for (const v of [c, f]) {
      expect(Number.isFinite(v.x)).toBe(true);
      expect(Number.isFinite(v.y)).toBe(true);
      expect(Number.isFinite(v.z)).toBe(true);
    }
  });
  it('zero-length bones return safely', () => {
    const h = hip();
    const c = new THREE.Vector3().copy(h);
    const f = new THREE.Vector3().copy(h);
    expect(() => solveTwoBoneIK(h, c, f, new THREE.Vector3(0, 0.2, 0.4))).not.toThrow();
  });
});

describe('legPole', () => {
  it('projects the knee direction perpendicular to hip→target', () => {
    const hip = new THREE.Vector3(0, 1, 0);
    const knee = new THREE.Vector3(0, 0.55, 0.3);
    const target = new THREE.Vector3(0, 0.1, 0.6);
    const pole = legPole(hip, knee, target, new THREE.Vector3());
    const d = target.clone().sub(hip).normalize();
    expect(Math.abs(pole.dot(d))).toBeLessThan(0.15);
  });
  it('falls back to a model-forward pole when the authored knee projects backward', () => {
    const hip = new THREE.Vector3(0, 1, 0);
    const knee = new THREE.Vector3(0, 1, -1); // straight behind
    const target = new THREE.Vector3(0.4, 0.6, 0.8); // off-axis forward target
    const pole = legPole(hip, knee, target, new THREE.Vector3());
    expect(pole.z).toBeGreaterThan(0);
  });
});
