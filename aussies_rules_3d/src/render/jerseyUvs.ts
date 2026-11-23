/**
 * Jersey number UVs — the kit garments in `gaelic_player.glb` ship with only
 * POSITION / NORMAL / JOINTS_0 / WEIGHTS_0 (no TEXCOORD_0), so `mat.map`
 * (the canvas-drawn squad number) would sample a single texel and the
 * jerseys render as flat club colours with no numbers.
 *
 * `jerseyNumberUvs` synthesises a chest/back projection at load time:
 *   - vertices facing front/back (|nz| dominant) project from (x, y); one side
 *     gets a mirrored U so the number reads correctly from BOTH sides;
 *   - side/top vertices collapse onto a background corner of the number
 *     texture (flat club colour), so nothing smears around the ribs.
 *
 * Pure math, covered in tests/jerseyUvs.spec.ts.
 */
import * as THREE from 'three';

/** Background corner of the number texture (safe flat-primary sample). */
export const KIT_BACKGROUND_UV: [number, number] = [0.03, 0.03];

export function jerseyNumberUvs(
  positions: ArrayLike<number>,
  normals: ArrayLike<number>
): Float32Array {
  const count = Math.floor(positions.length / 3);
  const uvs = new Float32Array(count * 2);
  let xMin = Infinity, xMax = -Infinity, yMin = Infinity, yMax = -Infinity;
  for (let i = 0; i < count; i++) {
    const x = positions[i * 3], y = positions[i * 3 + 1];
    if (x < xMin) xMin = x;
    if (x > xMax) xMax = x;
    if (y < yMin) yMin = y;
    if (y > yMax) yMax = y;
  }
  const sx = Math.max(1e-6, xMax - xMin);
  const sy = Math.max(1e-6, yMax - yMin);
  for (let i = 0; i < count; i++) {
    const x = positions[i * 3], y = positions[i * 3 + 1];
    const nz = normals[i * 3 + 2];
    const nx = normals[i * 3];
    let u: number, v: number;
    if (Math.abs(nz) >= Math.abs(nx) && Math.abs(nz) > 0.25) {
      u = (x - xMin) / sx;
      if (nz < 0) u = 1 - u; // back-facing side: mirror so the glyph reads correctly
      v = (y - yMin) / sy;
    } else {
      u = KIT_BACKGROUND_UV[0];
      v = KIT_BACKGROUND_UV[1];
    }
    uvs[i * 2] = u;
    uvs[i * 2 + 1] = v;
  }
  return uvs;
}

/** Apply synthesised number UVs to a geometry that lacks any (idempotent). */
export function ensureJerseyUvs(geometry: THREE.BufferGeometry): void {
  if (geometry.attributes.uv) return;
  const pos = geometry.attributes.position;
  const nor = geometry.attributes.normal;
  if (!pos || !nor) return;
  const uvs = jerseyNumberUvs(pos.array as ArrayLike<number>, nor.array as ArrayLike<number>);
  geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
}
