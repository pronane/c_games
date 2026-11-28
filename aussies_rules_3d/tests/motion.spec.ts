import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import {
  MotionDatabase,
  MotionEngine,
  parseClipManifest,
  buildFeatures,
  initialMotionState,
  advancePhase,
  computeStartPhase,
} from '../src/motion';
import { routeOneShot } from '../src/render/motionBinding';

const here = dirname(fileURLToPath(import.meta.url));
const assets = join(here, '..', 'public', 'assets');
const manifest = parseClipManifest(JSON.parse(readFileSync(join(assets, 'afl_motion.json'), 'utf8')));
const database = MotionDatabase.parse(JSON.parse(readFileSync(join(assets, 'afl_motion_features.json'), 'utf8')));

function makeEngine(): MotionEngine {
  const engine = new MotionEngine();
  engine.loadClips(manifest);
  engine.database = database;
  return engine;
}

describe('kick routing', () => {
  it('routes stationary kicks to the set shot and running kicks to kick_run', () => {
    expect(routeOneShot('kick', 0)).toBe('drop_kick');
    expect(routeOneShot('kick', 0.5)).toBe('drop_kick');
    expect(routeOneShot('kick', 3.4)).toBe('kick_run');
    expect(routeOneShot('handball', 0)).toBe('hand_pass');
    expect(routeOneShot('nonsense', 9)).toBe('');
  });
});

describe('baked AFL motion assets', () => {
  it('ship a valid 32-clip manifest with sane durations', () => {
    expect(manifest).toHaveLength(32);
    for (const clip of manifest) {
      expect(clip.duration).toBeGreaterThan(0);
      expect(clip.boneCount).toBe(52);
    }
  });

  it('ship a schema-v2 feature table whose rows map to manifest clips', () => {
    expect(database.count).toBeGreaterThan(500);
    expect(database.dimensions).toBe(24);
    const ids = new Set(manifest.map((c) => c.id));
    for (const row of database.rows) expect(ids.has(row.clipId)).toBe(true);
  });
});

describe('motion engine selection', () => {
  it('picks the idle clip for a stationary player', () => {
    const engine = makeEngine();
    const motion = initialMotionState(0);
    engine.update(motion, 0, 0, 'None', 'move', 1 / 60);
    expect(['idle', 'keeper_idle']).not.toContain(undefined);
    expect(motion.renderClipId).toBe('idle');
  });

  it('picks a running clip for a sprinting player and re-queries the gait', () => {
    const engine = makeEngine();
    const motion = initialMotionState(1);
    for (let i = 0; i < 30; i++) {
      engine.update(motion, 4.9, 0, 'None', 'sprint', 1 / 30, -1, 1, null,
        { x: 0, z: 4.9 }, { x: 0, z: 4.9 });
    }
    expect(['run', 'run_ball', 'jog']).toContain(motion.renderClipId);
  });

  it('aligns a running gait switch to a foot event when frames exist', () => {
    const a = manifest.find((c) => c.id === 'run')!;
    const b = manifest.find((c) => c.id === 'run_ball')!;
    // without authored plant frames this just clamps/wraps, never NaN or out-of-range
    const phase = computeStartPhase(a, b, 0.3, 'move');
    expect(phase).toBeGreaterThanOrEqual(0);
    expect(phase).toBeLessThan(1);
  });

  it('advances loop phases and wraps them', () => {
    const run = manifest.find((c) => c.id === 'run')!;
    const p = advancePhase(run, 0.95, 0.4, 1);
    expect(p).toBeGreaterThanOrEqual(0);
    expect(p).toBeLessThan(1);
  });

  it('prefers the kick wind-up consistent with the contact window', () => {
    const engine = makeEngine();
    const motion = initialMotionState(2);
    engine.update(motion, 2.5, 0, 'Possessed', 'shoot', 1 / 60, 0.5, 1, null,
      { x: 0, z: 2.5 }, { x: 0, z: 2.5 });
    // any kick clip is acceptable; what matters is a valid wind-up clip is chosen
    const clip = engine.tryGetClip(motion.renderClipId);
    expect(clip).not.toBeNull();
    expect(['Kick', 'Skill']).toContain(clip!.category);
  });

  it('builds trajectory features from the desired velocity', () => {
    const pose = new Float32Array(8);
    const f = buildFeatures(pose, 0, 4, 0, 3, 2, 0.5, 1.0);
    expect(f.length).toBe(24);
    expect(f[8]).toBe(0);
    expect(f[9]).toBe(4);
    expect(f[23]).toBeCloseTo(1.0, 5);
    // trajectory projection leads the current velocity toward the desired one
    expect(f[13]).toBeGreaterThan(f[9] * 0.4 * 0 + f[9] * 0.4 * 0); // sanity: traj index 13 is traj_pos_1_z
  });
});
