import { describe, expect, it } from 'vitest';
import * as THREE from 'three';
import { KIT_BACKGROUND_UV, ensureJerseyUvs, jerseyNumberUvs } from '../src/render/jerseyUvs';

// A tiny synthetic torso: front (nz>0), back (nz<0), sides (|nx|=1)
const positions = new Float32Array([
  0, 0, 0.5,   // 0 front bottom centre
  1, 0, 0.5,   // 1 front bottom right
  -1, 0, 0.5,  // 2 front bottom left
  0, 2, 0.5,   // 3 front top centre
  0, 0, -0.5,  // 4 back bottom centre
  1, 2, -0.5,  // 5 back top right
  1, 1, 0,     // 6 side (+x)
  0, 2, 0.5,   // 7 front top centre (dup)
]);
const normals = new Float32Array([
  0, 0, 1,
  0, 0, 1,
  0, 0, 1,
  0, 0, 1,
  0, 0, -1,
  0, 0, -1,
  1, 0, 0,
  0, 0, 1,
]);

describe('jerseyNumberUvs', () => {
  it('centres front chest on the glyph', () => {
    const uv = jerseyNumberUvs(positions, normals);
    const u0 = uv[0 * 2], u3 = uv[3 * 2];
    expect(u0).toBeCloseTo(0.5, 5);                      // centre → middle of the texture
    expect(uv[1 * 2]).toBeCloseTo(1.0, 5);               // front right edge
    expect(uv[2 * 2]).toBeCloseTo(0.0, 5);               // front left edge
    expect(u3).toBeCloseTo(0.5, 5);
    expect(uv[0 * 2 + 1]).toBeCloseTo(0.0, 5);           // bottom → v 0
    expect(uv[3 * 2 + 1]).toBeCloseTo(1.0, 5);           // top → v 1
  });

  it('mirrors u on the back so the glyph reads correctly both ways', () => {
    const uv = jerseyNumberUvs(positions, normals);
    // back bottom centre: u stays 0.5 (symmetric)
    expect(uv[4 * 2]).toBeCloseTo(0.5, 5);
    // back top RIGHT: mirrored → u should equal front LEFT (1-u), not front right
    expect(uv[5 * 2]).toBeCloseTo(0.0, 5);
  });

  it('collapses side/top verts onto the flat background corner', () => {
    const uv = jerseyNumberUvs(positions, normals);
    expect(uv[6 * 2]).toBeCloseTo(KIT_BACKGROUND_UV[0], 6);
    expect(uv[6 * 2 + 1]).toBeCloseTo(KIT_BACKGROUND_UV[1], 6);
  });
});

describe('ensureJerseyUvs', () => {
  it('adds an uv attribute to a geometry that lacks one', () => {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(positions.slice(), 3));
    g.setAttribute('normal', new THREE.BufferAttribute(normals.slice(), 3));
    expect(g.attributes.uv).toBeUndefined();
    ensureJerseyUvs(g);
    expect(g.attributes.uv).toBeDefined();
    expect(g.attributes.uv.count).toBe(8);
    expect(g.attributes.uv.itemSize).toBe(2);
  });

  it('is idempotent — existing UVs are left untouched', () => {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(positions.slice(), 3));
    g.setAttribute('normal', new THREE.BufferAttribute(normals.slice(), 3));
    const mine = new Float32Array(16).fill(0.77);
    g.setAttribute('uv', new THREE.BufferAttribute(mine, 2));
    ensureJerseyUvs(g);
    expect(g.attributes.uv.array[0]).toBeCloseTo(0.77, 6);
  });
});
