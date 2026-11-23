import { describe, expect, it } from 'vitest';
import { contrastInk, patternGeometry } from '../src/render/guernsey';

const W = 512, H = 512;

describe('patternGeometry', () => {
  it('vstripes: bars alternate with 50% coverage inside bounds', () => {
    const g = patternGeometry('vstripes', W, H);
    if (g.kind !== 'vstripes') throw new Error('wrong kind');
    expect(g.bars.length).toBe(6);
    const covered = g.bars.reduce((n, b) => n + b.w, 0);
    expect(covered / W).toBeGreaterThan(0.45);
    expect(covered / W).toBeLessThan(0.55);
    for (const b of g.bars) {
      expect(b.x).toBeGreaterThanOrEqual(0);
      expect(b.x + b.w).toBeLessThanOrEqual(W);
    }
  });

  it('hstripes: two hoops, ordered and inside bounds', () => {
    const g = patternGeometry('hstripes', W, H);
    if (g.kind !== 'hstripes') throw new Error('wrong kind');
    expect(g.hoops.length).toBe(2);
    expect(g.hoops[0].y + g.hoops[0].h).toBeLessThan(g.hoops[1].y);
    for (const hp of g.hoops) {
      expect(hp.y).toBeGreaterThanOrEqual(0);
      expect(hp.y + hp.h).toBeLessThanOrEqual(H);
      expect(hp.h).toBeGreaterThan(0);
    }
  });

  it('sash: single diagonal band with sane angle and width', () => {
    const g = patternGeometry('sash', W, H);
    if (g.kind !== 'sash') throw new Error('wrong kind');
    expect(g.angle).toBeGreaterThan(0.3);
    expect(g.angle).toBeLessThan(0.9);
    expect(g.width).toBeGreaterThan(40);
    expect(g.width).toBeLessThan(200);
  });

  it('solid: no shapes painted', () => {
    expect(patternGeometry('solid', W, H)).toEqual({ kind: 'solid' });
  });
});

describe('contrastInk', () => {
  it('picks dark ink on light fills and light ink on dark fills', () => {
    expect(contrastInk('#f2f2f2')).toBe('#101010');
    expect(contrastInk('#0b2545')).toBe('#f5f5f5');
    expect(contrastInk('#ffd23f')).toBe('#101010');
    expect(contrastInk('#1a1a1a')).toBe('#f5f5f5');
    expect(contrastInk('not-a-color')).toBe('#f5f5f5');
  });
});
