/**
 * Level-of-detail plumbing for skinned squad parts (Sprite Forge skinlod).
 *
 * `tools/build_afl_lods.py` bakes `<part>_lod1` / `<part>_lod2` nodes next to
 * every full-detail part (same skin, same material, kit naming preserved so
 * runtime tinting still matches). This module decides which level is shown:
 *
 *   - `lodLevelOf` / `basePartName` — parse the `_lod1` / `_lod2` suffix
 *   - `collectLodKits(root)`    — group a cloned player's parts into kits
 *   - `setLodLevel(kits, lod)`  — flip visibility (base only by default)
 *   - `pickLodLevel(dist, d)`   — broadcast distance → level
 *
 * With the shipped asset (no LOD nodes) `collectLodKits` returns an empty
 * list and the per-frame work is skipped — behaviour is unchanged.
 */
import * as THREE from 'three';

export type LodLevel = 0 | 1 | 2;

const LOD_RE = /^(.*)_lod([12])$/;

/** 0 when the name carries no suffix, else the LOD index it declares. */
export function lodLevelOf(name: string): LodLevel {
  const m = LOD_RE.exec(name ?? '');
  return m ? (Number(m[2]) as LodLevel) : 0;
}

/** Strip a trailing `_lod1` / `_lod2` so kit-suffix matching still works. */
export function basePartName(name: string): string {
  const m = LOD_RE.exec(name ?? '');
  return m ? m[1] : (name ?? '');
}

export interface LodKit {
  /** The full-detail node (always present for a kit to be returned). */
  base: THREE.Object3D;
  lod1: THREE.Object3D | null;
  lod2: THREE.Object3D | null;
}

/**
 * Group `x`, `x_lod1`, `x_lod2` triples under a (possibly cloned) player root.
 * Only bases that have at least one LOD sibling are returned, so the list is
 * empty for GLBs without LOD data.
 */
export function collectLodKits(root: THREE.Object3D): LodKit[] {
  const kits = new Map<string, LodKit>();
  root.traverse((o) => {
    const m = LOD_RE.exec(o.name ?? '');
    if (!m) return;
    const key = m[1];
    let kit = kits.get(key);
    if (!kit) {
      kit = { base: null as unknown as THREE.Object3D, lod1: null, lod2: null };
      kits.set(key, kit);
    }
    if (m[2] === '1') kit.lod1 = o;
    else kit.lod2 = o;
  });
  root.traverse((o) => {
    const n = o.name ?? '';
    if (LOD_RE.test(n)) return;
    const kit = kits.get(n);
    if (kit && !kit.base) kit.base = o;
  });
  const out: LodKit[] = [];
  for (const kit of kits.values()) {
    if (kit.base) out.push(kit);
  }
  return out;
}

export type LodQuality = 'ultra' | 'high' | 'performance';

/** Switch distances (metres) per quality tier — mirrors `LOD_PLAN['distances_m']` in Sprite Forge. */
export const LOD_DISTANCES: Record<LodQuality, [number, number]> = {
  ultra: [22, 48],
  high: [16, 36],
  performance: [11, 26],
};

/** Normalise a <select> value to a quality tier (anything unexpected → high). */
export function pickLodQuality(value: string | undefined): LodQuality {
  return value === 'ultra' || value === 'performance' ? value : 'high';
}

/** Level for a camera→player distance. */
export function pickLodLevel(distance: number, d: [number, number]): LodLevel {
  if (!(distance > d[0])) return 0;
  if (!(distance > d[1])) return 1;
  return 2;
}

/**
 * Show exactly one member of each kit. Missing levels fall back to the nearest
 * available one; `level === 0` always shows the full-detail base.
 */
export function setLodLevel(kits: LodKit[], level: LodLevel): void {
  for (const kit of kits) {
    const pick =
      level === 0 ? kit.base
      : level === 1 ? (kit.lod1 ?? kit.lod2 ?? kit.base)
      : (kit.lod2 ?? kit.lod1 ?? kit.base);
    kit.base.visible = pick === kit.base;
    if (kit.lod1) kit.lod1.visible = pick === kit.lod1;
    if (kit.lod2) kit.lod2.visible = pick === kit.lod2;
  }
}
