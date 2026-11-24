import { describe, expect, it } from 'vitest';
import { parseAbStats, summariseLeg } from '../tools/ab_stats.mjs';

const LOG = `
noise
AB_STATS fps=59.2 p50_ms=16.4 p95_ms=22.1 tris=51230 calls=341 textures=27 geometries=18 lod=high
more noise
AB_STATS fps=57.9 p50_ms=17.0 p95_ms=24.8 tris=51230 calls=339 textures=27 geometries=18 lod=high
AB_STATS fps=61.3 p50_ms=15.9 p95_ms=21.2 tris=51244 calls=355 textures=27 geometries=18 lod=high
`;

describe('parseAbStats', () => {
  it('extracts every AB_STATS sample in order', () => {
    const samples = parseAbStats(LOG);
    expect(samples).toHaveLength(3);
    expect(samples[0]).toEqual({
      fps: 59.2, p50_ms: 16.4, p95_ms: 22.1,
      tris: 51230, calls: 341, textures: 27, geometries: 18, lod: 'high',
    });
    expect(samples[2].tris).toBe(51244);
    expect(samples.map((s) => s.lod)).toEqual(['high', 'high', 'high']);
  });
  it('ignores lines that are not AB_STATS', () => {
    expect(parseAbStats('nothing here\nAB_STATS fps=broken')).toEqual([]);
    expect(parseAbStats('')).toEqual([]);
  });
});

describe('summariseLeg', () => {
  it('renders an empty leg without crashing', () => {
    const row = summariseLeg('lod', []);
    expect(row).toContain('`lod`');
    expect(row).toContain('0');
    expect(row).toContain('no samples');
  });
  it('aggregates avg/min fps, max p50/p95, and last-sample counters', () => {
    const row = summariseLeg('original', parseAbStats(LOG));
    expect(row).toContain('| `original` | 3 |');
    expect(row).toContain('59.5 / 57.9'); // fps avg / min
    expect(row).toContain('16.4 / 17.0'); // p50 avg / max
    expect(row).toContain('22.7 / 24.8'); // p95 avg / max
    expect(row).toContain('51244'); // last tris, not the mean
    expect(row).toContain('high');
  });
});
