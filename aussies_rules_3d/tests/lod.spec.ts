/**
 * Unit tests for the skinned-mesh LOD plumbing (`src/render/lod.ts`).
 * The GLB-specific bake path is covered by `tools/build_afl_lods.py`'s
 * report (tools/out/lod_report.json); here we pin the pure selection logic
 * and the visibility switching.
 */
import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import {
  basePartName,
  collectLodKits,
  LOD_DISTANCES,
  lodLevelOf,
  pickLodLevel,
  setLodLevel,
  type LodKit,
} from '../src/render/lod';

describe('lodLevelOf / basePartName', () => {
  it('parses plain and suffixed names', () => {
    expect(lodLevelOf('v3_jersey')).toBe(0);
    expect(lodLevelOf('v3_jersey_lod1')).toBe(1);
    expect(lodLevelOf('v3_jersey_lod2')).toBe(2);
    expect(basePartName('v3_jersey')).toBe('v3_jersey');
    expect(basePartName('v3_jersey_lod1')).toBe('v3_jersey');
    expect(basePartName('v3_jersey_lod2')).toBe('v3_jersey');
  });

  it('does not strip lookalikes', () => {
    expect(basePartName('v3_lodger')).toBe('v3_lodger'); // no _lodN suffix
    expect(lodLevelOf('v3_lodger')).toBe(0);
    expect(basePartName('shine_lod')).toBe('shine_lod');
  });
});

describe('pickLodLevel', () => {
  const d: [number, number] = LOD_DISTANCES.high; // [16, 36]
  it('switches at the tier thresholds', () => {
    expect(pickLodLevel(0, d)).toBe(0);
    expect(pickLodLevel(16, d)).toBe(0); // boundary stays on the full mesh
    expect(pickLodLevel(16.1, d)).toBe(1);
    expect(pickLodLevel(36, d)).toBe(1);
    expect(pickLodLevel(36.1, d)).toBe(2);
    expect(pickLodLevel(200, d)).toBe(2);
  });
});

function named(name: string): THREE.Object3D {
  const o = new THREE.Object3D();
  o.name = name;
  return o;
}

function makePlayer(): { root: THREE.Group; parts: Record<string, THREE.Object3D> } {
  const root = new THREE.Group();
  const parts: Record<string, THREE.Object3D> = {};
  for (const n of ['v0_jersey', 'v0_jersey_lod1', 'v0_jersey_lod2', 'v0_eyes',
    'v0_lashes', 'v0_lashes_lod1', 'v0_hair', 'v0_hair_lod1', 'v0_hair_lod2']) {
    const o = named(n);
    parts[n] = o;
    root.add(o);
  }
  return { root, parts };
}

describe('collectLodKits', () => {
  it('groups triples and pairs, ignores parts without LODs', () => {
    const { root } = makePlayer();
    const kits = collectLodKits(root);
    const bases = kits.map((k) => k.base.name).sort();
    expect(bases).toEqual(['v0_hair', 'v0_jersey', 'v0_lashes']);
    const lashes = kits.find((k) => k.base.name === 'v0_lashes')!;
    expect(lashes.lod1?.name).toBe('v0_lashes_lod1');
    expect(lashes.lod2).toBeNull(); // dropped at level 2 in the bake plan
  });

  it('returns [] for a GLB with no LOD data', () => {
    const root = new THREE.Group();
    root.add(named('v0_jersey'), named('v0_body'));
    expect(collectLodKits(root)).toEqual([]);
  });
});

describe('setLodLevel', () => {
  it('shows base at 0, lod1 at 1, lod2 at 2', () => {
    const { root, parts } = makePlayer();
    const kits: LodKit[] = collectLodKits(root);
    setLodLevel(kits, 1);
    expect(parts['v0_jersey'].visible).toBe(false);
    expect(parts['v0_jersey_lod1'].visible).toBe(true);
    expect(parts['v0_jersey_lod2'].visible).toBe(false);
    // lashes has no lod2 → falls back to lod1 at level 2
    setLodLevel(kits, 2);
    expect(parts['v0_lashes'].visible).toBe(false);
    expect(parts['v0_lashes_lod1'].visible).toBe(true);
    expect(parts['v0_jersey_lod2'].visible).toBe(true);
    setLodLevel(kits, 0);
    expect(parts['v0_jersey'].visible).toBe(true);
    expect(parts['v0_jersey_lod1'].visible).toBe(false);
    expect(parts['v0_jersey_lod2'].visible).toBe(false);
  });

  it('parts without LOD siblings are never hidden', () => {
    const { root, parts } = makePlayer();
    const kits = collectLodKits(root);
    setLodLevel(kits, 2);
    expect(parts['v0_eyes'].visible).toBe(true);
  });
});
