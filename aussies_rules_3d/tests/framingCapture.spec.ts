import { describe, it, expect } from 'vitest';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const sample = (ball = '100.0', player = '100.0') =>
  `AB_CAMSTAT frames=2 ball_in=${ball} player_in=${player} ball_max_ndc=0.70 player_max_ndc=${player === 'na' ? 'na' : '0.60'}\n`;
function check(text: string | null, requirePlayer = false) {
  const dir = mkdtempSync(join(tmpdir(), 'camera-test-'));
  try {
    const file = join(dir, 'console.log');
    if (text !== null) writeFileSync(file, text);
    return spawnSync(process.execPath, ['tools/check_framing.mjs', ...(requirePlayer ? ['--require-player'] : []), file], { encoding: 'utf8' });
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}
describe('capture visibility gate', () => {
  it('passes ball-only attract coverage without claiming player coverage', () => {
    expect(check(sample('100.0', 'na').repeat(2)).status).toBe(0);
  });
  it('requires observed player samples for a match capture', () => {
    expect(check(sample().repeat(2), true).status).toBe(0);
    expect(check(sample('100.0', 'na').repeat(2), true).status).toBe(1);
  });
  it('rejects missing and insufficient samples', () => {
    for (const text of [null, '', sample()]) expect(check(text).status).toBe(1);
  });
  it('annotates offending values rather than just saying FAIL', () => {
    const result = check(sample('99.0').repeat(2));
    expect(result.status).toBe(1);
    expect(result.stderr).toContain('::error::');
    expect(result.stderr).toContain('"ball_in":99');
  });
  it('rejects an excessive peak even when percentage rounds to 100', () => {
    expect(check(sample().replace('0.70', '0.90').repeat(2)).status).toBe(1);
  });
});
