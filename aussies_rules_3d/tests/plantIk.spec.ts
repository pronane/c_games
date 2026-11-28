import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { solveLegChainWorld, aimBoneWorld, parsePlantIkFlag } from '../src/render/motionBinding';

/** Build a synthetic thigh→calf→foot chain under a yawed root, like the GLB. */
function makeLeg(footOffsetZ: number) {
  const root = new THREE.Group();
  root.position.set(3, 0, -2);
  root.rotation.y = Math.PI / 3;
  const thigh = new THREE.Group();
  thigh.name = 'thigh_l';
  thigh.position.set(0.1, 0.95, 0.02);
  root.add(thigh);
  const calf = new THREE.Group();
  calf.name = 'calf_l';
  calf.position.set(0, -0.55, 0.05); // local to thigh
  thigh.add(calf);
  const foot = new THREE.Group();
  foot.name = 'foot_l';
  foot.position.set(0, -0.57, 0.02); // local to calf
  calf.add(foot);
  // give the thigh an initial rotation so the solve isn't starting from identity
  thigh.rotation.x = -0.15;
  calf.rotation.x = 0.35;
  root.updateMatrixWorld(true);
  void footOffsetZ;
  return { root, thigh, calf, foot };
}

describe('solveLegChainWorld', () => {
  it('preserves segment lengths and lands the foot on the target', () => {
    const { root, thigh, calf, foot } = makeLeg(0);
    const l1 = thigh.getWorldPosition(new THREE.Vector3())
      .distanceTo(calf.getWorldPosition(new THREE.Vector3()));
    const l2 = calf.getWorldPosition(new THREE.Vector3())
      .distanceTo(foot.getWorldPosition(new THREE.Vector3()));
    const target = new THREE.Vector3(3.1, 0.15, -1.55); // ~0.96 m from hip, well inside reach
    const ok = solveLegChainWorld(thigh, calf, foot, target, new THREE.Vector3(1, 0, 0), root);
    expect(ok).toBe(true);
    const footW = foot.getWorldPosition(new THREE.Vector3());
    expect(footW.distanceTo(target)).toBeLessThan(1e-4);
    const kneeW = calf.getWorldPosition(new THREE.Vector3());
    const hipW = thigh.getWorldPosition(new THREE.Vector3());
    expect(hipW.distanceTo(kneeW)).toBeCloseTo(l1, 5);
    expect(kneeW.distanceTo(footW)).toBeCloseTo(l2, 5);
    expect(Number.isFinite(kneeW.x + kneeW.y + kneeW.z)).toBe(true);
  });
  it('clamps an unreachable target instead of NaNing', () => {
    const { root, thigh, calf, foot } = makeLeg(0);
    const target = new THREE.Vector3(50, 0.08, 50);
    const ok = solveLegChainWorld(thigh, calf, foot, target, new THREE.Vector3(1, 0, 0), root);
    expect(ok).toBe(true);
    const footW = foot.getWorldPosition(new THREE.Vector3());
    expect(Number.isFinite(footW.x + footW.y + footW.z)).toBe(true);
    const hipW = thigh.getWorldPosition(new THREE.Vector3());
    expect(hipW.distanceTo(footW)).toBeLessThan(
      hipW.distanceTo(new THREE.Vector3(50, 0.08, 50))); // didn't chase to the moon
  });
  it('identical repeated solves are deterministic', () => {
    const run = () => {
      const { root, thigh, calf, foot } = makeLeg(0);
      solveLegChainWorld(thigh, calf, foot, new THREE.Vector3(3.2, 0.08, -1.6), new THREE.Vector3(0, 0, 1), root);
      return [
        thigh.getWorldPosition(new THREE.Vector3()).toArray(),
        calf.getWorldPosition(new THREE.Vector3()).toArray(),
        foot.getWorldPosition(new THREE.Vector3()).toArray(),
      ];
    };
    expect(run()).toEqual(run());
  });
});

describe('aimBoneWorld', () => {
  it('rotates the bone so its fromDir aligns with toDir in world space', () => {
    const root = new THREE.Group();
    root.rotation.y = 1.1;
    root.position.set(0, 0, 0);
    const bone = new THREE.Group();
    bone.position.set(0, 1, 0);
    bone.rotation.z = 0.3;
    root.add(bone);
    const child = new THREE.Group();
    child.position.set(0.0, -0.4, 0.0);
    bone.add(child);
    root.updateMatrixWorld(true);
    const fromDir = child.getWorldPosition(new THREE.Vector3())
      .sub(bone.getWorldPosition(new THREE.Vector3()));
    const toDir = new THREE.Vector3(0.6, -1.0, 0.35);
    aimBoneWorld(bone, fromDir, toDir);
    root.updateMatrixWorld(true);
    const after = child.getWorldPosition(new THREE.Vector3())
      .sub(bone.getWorldPosition(new THREE.Vector3()))
      .normalize();
    expect(after.dot(toDir.clone().normalize())).toBeGreaterThan(0.999);
  });
});

describe('parsePlantIkFlag', () => {
  it('is on only for plantik=1', () => {
    expect(parsePlantIkFlag('?plantik=1')).toBe(true);
    expect(parsePlantIkFlag('?ab=1&plantik=1')).toBe(true);
    expect(parsePlantIkFlag('?plantik=0')).toBe(false);
    expect(parsePlantIkFlag('?plantik=true')).toBe(false);
    expect(parsePlantIkFlag('')).toBe(false);
    expect(parsePlantIkFlag('?other=1')).toBe(false);
    expect(parsePlantIkFlag('?plantik=')).toBe(false);
  });
});
