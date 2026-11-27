import { it, expect } from 'vitest';
import { mkdirSync, writeFileSync } from 'node:fs';
import { MatchSim } from '../src/sim/match';
import { AFL_SETTINGS } from '../src/rules/types';
import { captureIntent } from '../src/sim/captureScenario';

it('audits seeded gameplay flow without treating aggregate numbers as visual acceptance', () => {
  const reports = [];
  for (const seed of [11, 42, 123]) {
    const sim = new MatchSim({ ...AFL_SETTINGS, seed, quarterSeconds: 300 }); sim.start();
    const reasons: Record<string, number> = {};
    let crowd = 0, crowdSamples = 0, backwards = 0, runningSamples = 0;
    for (let tick = 0; tick < 3600; tick++) {
      for (const event of sim.update(1 / 60, captureIntent(tick))) {
        const key = `${event.type}:${event.text ?? ''}`;
        reasons[key] = (reasons[key] ?? 0) + 1;
      }
      if (tick % 30 === 0) {
        const b = sim.state.ball;
        if (sim.state.phase === 'live') {
          crowd += sim.state.players.filter(p => !p.onBench && Math.hypot(p.x - b.x, p.z - b.z) < 5).length;
          crowdSamples++;
        }
        for (const p of sim.state.players) {
          if (p.onBench || Math.hypot(p.vx, p.vz) < 3) continue;
          runningSamples++;
          if (p.vx * Math.cos(p.facing) + p.vz * Math.sin(p.facing) < 0) backwards++;
        }
      }
    }
    expect(Object.keys(reasons).length).toBeGreaterThan(0);
    expect(sim.diagnostics.liveSeconds).toBeGreaterThan(0);
    reports.push({ seed, simulatedSeconds: 60, diagnostics: sim.diagnostics,
      meanLiveCrowd5: crowd / Math.max(1, crowdSamples), backwards, runningSamples, events: reasons });
  }
  mkdirSync('build/gameplay-audit', { recursive: true });
  writeFileSync('build/gameplay-audit/simulation.json', JSON.stringify(reports, null, 2));
}, 20000);
