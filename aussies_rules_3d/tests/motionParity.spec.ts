/**
 * Parity + robustness suite for the TS port of the Arena Motion Engine.
 *
 * There is no .NET runtime in this environment, so C#-vs-TS execution parity
 * cannot be run here; instead the search is verified against an independent
 * brute-force reference inside this file, and the query builder/normalisation
 * are pinned with hand-computed golden values. The port was line-by-line from
 * arena-fc Scripts/Core/Animation/; arena-fc CI remains the semantic gate for
 * the C# side.
 */
import { describe, expect, it } from 'vitest';
import {
  MotionDatabase,
  MotionFormatError,
  buildFeatures,
  initialPhase,
  groupWeights,
  NO_CONTACT,
} from '../src/motion';
import { DIMENSIONS, TIME_TO_CONTACT } from '../src/motion/motionFeatureLayout';

function makeDb(rows: unknown[]): unknown {
  return {
    version: 2,
    featureSchemaVersion: 2,
    dimensions: DIMENSIONS,
    layout: [
      'foot_l_pos_x', 'foot_l_pos_z', 'foot_r_pos_x', 'foot_r_pos_z',
      'foot_l_vel_x', 'foot_l_vel_z', 'foot_r_vel_x', 'foot_r_vel_z',
      'root_vel_x', 'root_vel_z', 'yaw_rate',
      'traj_pos_0_x', 'traj_pos_0_z', 'traj_pos_1_x', 'traj_pos_1_z',
      'traj_pos_2_x', 'traj_pos_2_z',
      'traj_dir_0_x', 'traj_dir_0_z', 'traj_dir_1_x', 'traj_dir_1_z',
      'traj_dir_2_x', 'traj_dir_2_z',
      'time_to_contact',
    ],
    trajectoryTimes: [0.2, 0.4, 0.6],
    space: 'facing_root_xz',
    normalization: {
      method: 'zscore',
      mean: new Array(DIMENSIONS).fill(0),
      stdDev: new Array(DIMENSIONS).fill(1),
    },
    weights: groupWeights(),
    rows,
  };
}
function row(clipId: string, frameIndex: number, phase: number, category = 'Locomotion',
  ballState = 'None', features?: number[]): unknown {
  return {
    clipId, frameIndex, phase, category, ballState, styleTag: '',
    features: features ?? new Array(DIMENSIONS).fill(0),
  };
}

describe('query builder (hand-computed)', () => {
  it('builds the damped-pursuit trajectory', () => {
    const zero = new Float32Array(8);
    const f = buildFeatures(zero, 0, 4, 0, 0, 0, 0, NO_CONTACT);
    // desired = 0, current = (0,4): traj1 = 0*t + (4-0)*(1-e^{-4t})*0.25
    const t2 = 0.4;
    const expected = 4 * (1 - Math.exp(-4 * t2)) * 0.25;
    expect(f[12 + 2]).toBeCloseTo(expected, 5); // traj_pos_1_z
    expect(f[TIME_TO_CONTACT]).toBe(NO_CONTACT);
    expect(f.length).toBe(DIMENSIONS);
  });

  it('places yaw sine/cosine in the facing dims', () => {
    const zero = new Float32Array(8);
    const f = buildFeatures(zero, 0, 1, 0, 0, 1, 0.5, NO_CONTACT);
    // yaw = desiredYawRate * t ; t = .2/.4/.6
    expect(f[17]).toBeCloseTo(Math.sin(0.5 * 0.2), 6);
    expect(f[18]).toBeCloseTo(Math.cos(0.5 * 0.2), 6);
    expect(f[21]).toBeCloseTo(Math.sin(0.5 * 0.6), 6);
    expect(f[22]).toBeCloseTo(Math.cos(0.5 * 0.6), 6);
  });

  it('clamps time_to_contact into [0, NO_CONTACT] and rejects NaN inputs', () => {
    const zero = new Float32Array(8);
    const f = buildFeatures(zero, 0, 0, 0, 0, 0, 0, 99);
    expect(f[TIME_TO_CONTACT]).toBe(NO_CONTACT);
    expect(() => buildFeatures(zero, NaN, 0, 0, 0, 0, 0)).toThrow(MotionFormatError);
  });
});

describe('database search (independent brute force reference)', () => {
  const rows = [
    row('aaa_run', 0, 0.0, 'Locomotion', 'None', new Array(DIMENSIONS).fill(0)),
    row('bbb_jog', 0, 0.0, 'Locomotion', 'None', (() => { const a = new Array(DIMENSIONS).fill(0); a[9] = 3; return a; })()),
    row('ccc_idle', 0, 0.0, 'Idle', 'None', (() => { const a = new Array(DIMENSIONS).fill(0); a[9] = 6; return a; })()),
  ];
  const db = MotionDatabase.parse(makeDb(rows));

  it('matches the closest row by weighted squared z-error', () => {
    const features = new Float32Array(DIMENSIONS);
    features[9] = 2.8; // much nearer the jog row than the run row
    const match = db.trySearch({ features, category: 'Locomotion', ball: 'None', intent: 'move' });
    expect(match).not.toBeNull();
    expect(match!.row.clipId).toBe('bbb_jog');
    // reference: argmin over eligible rows of sum w_d * (q - r)^2  (mean 0, std 1 here)
    const weights = groupWeights();
    const costOf = (r: Float32Array) => weights.reduce((acc, w, d) => acc + w * (features[d] - r[d]) ** 2, 0);
    const costs = rows.map((r) => costOf(Float32Array.from((r as { features: number[] }).features)));
    expect(match!.cost).toBeCloseTo(Math.min(...costs), 4);
  });

  it('applies the current-clip switch penalty', () => {
    const features = new Float32Array(DIMENSIONS);
    features[9] = 2.9; // near bbb_jog, far from aaa_run
    const same = db.trySearch({ features, category: 'Locomotion', ball: 'None', intent: 'move',
      currentClipId: 'aaa_run', currentPhase: 0, switchPenalty: 0.08, temporalPenalty: 0.12 });
    expect(same!.row.clipId).toBe('bbb_jog');
    // with a huge switch penalty the incumbent wins instead
    const sticky = db.trySearch({ features, category: 'Locomotion', ball: 'None', intent: 'move',
      currentClipId: 'aaa_run', currentPhase: 0, switchPenalty: 1000, temporalPenalty: 0.12 });
    expect(sticky!.row.clipId).toBe('aaa_run');
  });

  it('refuses the locomotion table for a non-locomotion intent', () => {
    const features = new Float32Array(DIMENSIONS);
    const match = db.trySearch({ features, category: 'Locomotion', ball: 'None', intent: 'action' });
    expect(match).toBeNull();
  });

  it('one-shot action search ignores dedicated rows and other categories', () => {
    const actionRows = [
      row('kick_a', 0, 0, 'Kick', 'Possessed', new Array(DIMENSIONS).fill(0)),
      { clipId: 'kick_b', frameIndex: 0, phase: 0, category: 'Kick', ballState: 'Possessed', styleTag: 'dedicated',
        features: new Array(DIMENSIONS).fill(0) },
      row('run_x', 0, 0, 'Locomotion', 'None', new Array(DIMENSIONS).fill(0)),
    ];
    const adb = MotionDatabase.parse(makeDb(actionRows));
    const match = adb.trySearch({ features: new Float32Array(DIMENSIONS), category: 'Kick', ball: 'Possessed', intent: 'action' });
    expect(match!.row.clipId).toBe('kick_a');
  });

  it('forced-clip search considers only that clip', () => {
    const features = new Float32Array(DIMENSIONS);
    const match = db.trySearch({ features, category: 'Kick', ball: 'None', intent: 'action', forcedClipId: 'ccc_idle' });
    expect(match!.row.clipId).toBe('ccc_idle');
  });

  it('rejects malformed databases', () => {
    expect(() => MotionDatabase.parse(makeDb([]))).toThrow(MotionFormatError);
    expect(() => MotionDatabase.parse({ ...makeDb([row('a', 0, 0)]) as object, version: 3 })).toThrow(MotionFormatError);
    const dup = [row('dup', 0, 0), row('dup', 0, 0.5)];
    expect(() => MotionDatabase.parse(makeDb(dup))).toThrow(MotionFormatError);
  });
});

describe('misc engine contracts', () => {
  it('staggers phases deterministically by player index', () => {
    expect(initialPhase(0)).toBe(initialPhase(0));
    expect(initialPhase(0)).not.toBe(initialPhase(1));
    expect(initialPhase(3)).toBeGreaterThanOrEqual(0);
    expect(initialPhase(3)).toBeLessThan(1);
  });

  it('weights match the documented contract', () => {
    const w = groupWeights();
    expect(w[4]).toBe(1.3);
    expect(w[9]).toBe(0.8);
    expect(w[10]).toBe(0.7);
    expect(w[11]).toBe(1.5);
    expect(w[17]).toBe(1.2);
    expect(w[TIME_TO_CONTACT]).toBe(12.0);
  });
});
