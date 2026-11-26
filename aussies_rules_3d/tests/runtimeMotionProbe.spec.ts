import { describe, expect, it } from 'vitest';
import { MotionProbe } from '../src/render/motionProbe';
import { TeamPlan } from '../src/sim/teamPlan';
import { MatchSim } from '../src/sim/match';
import { AFL_SETTINGS } from '../src/rules/types';

const feet = (x: number, contact = true) => [{ x, y: 0, z: 0, contact }];
describe('runtime motion evidence', () => {
  it('measures continuous backwards travel using rendered forward, not requested heading', () => {
    const probe = new MotionProbe();
    for (let i = 0; i < 30; i++) probe.observe(1, { x: -5, z: 0 }, { x: 1, z: 0 }, [], 1 / 60);
    expect(probe.snapshot().maxBackwardsSeconds).toBeCloseTo(0.5);
  });
  it('measures foot displacement only across consecutive contact samples', () => {
    const probe = new MotionProbe();
    probe.observe(1, { x: 0, z: 0 }, { x: 1, z: 0 }, feet(0), 0.1);
    probe.observe(1, { x: 0, z: 0 }, { x: 1, z: 0 }, feet(0.1), 0.1);
    expect(probe.snapshot().meanContactFootSpeed).toBeCloseTo(1);
    probe.observe(1, { x: 0, z: 0 }, { x: 1, z: 0 }, feet(10, false), 0.1);
    expect(probe.snapshot().contactFootSamples).toBe(1);
  });
  it('does not count a player switch as a huge sliding foot', () => {
    const probe = new MotionProbe();
    probe.observe(1, { x: 0, z: 0 }, { x: 1, z: 0 }, feet(0), 0.1);
    probe.observe(2, { x: 0, z: 0 }, { x: 1, z: 0 }, feet(100), 0.1);
    expect(probe.snapshot().meanContactFootSpeed).toBeNull();
    probe.observe(2, { x: 0, z: 0 }, { x: 1, z: 0 }, feet(100), 0);
    expect(probe.snapshot().samples).toBe(2);
  });
});

describe('team plan restart and roster ownership', () => {
  it('invalidates pressure jobs immediately on restart without waiting for the hold timer', () => {
    const sim = new MatchSim({ ...AFL_SETTINGS, seed: 42 }); sim.start();
    sim.state.phase = 'live';
    const plan = new TeamPlan();
    const live = plan.update(sim.state, 1 / 60);
    expect([...live.values()].some(job => job.kind === 'contest')).toBe(true);
    sim.state.phase = 'ballUp';
    const restart = plan.update(sim.state, 1 / 60);
    expect(restart).not.toBe(live);
    expect([...restart.values()].every(job => job.kind !== 'contest')).toBe(true);
    expect([...restart.values()].filter(job => job.kind === 'stage')).toHaveLength(4);
    sim.state.phase = 'live';
    expect(plan.update(sim.state, 1 / 60)).not.toBe(restart);
  });
  it('removes benched players immediately rather than leaving a vacant contest job', () => {
    const sim = new MatchSim({ ...AFL_SETTINGS, seed: 42 }); sim.start();
    sim.state.phase = 'live';
    const plan = new TeamPlan();
    const jobs = plan.update(sim.state, 1 / 60);
    const id = [...jobs].find(([, job]) => job.kind === 'contest')![0];
    sim.state.players.find(p => p.id === id)!.onBench = true;
    const next = plan.update(sim.state, 1 / 60);
    expect(next.has(id)).toBe(false);
    expect([...next.values()].filter(job => job.kind === 'contest')).toHaveLength(4);
    expect(plan.diagnostics.replans).toBe(2);
  });
});

import { aiIntentFor } from '../src/sim/ai';
it('assigns aerial contests at the drop point and runs there before the ball comes within 9m', () => {
  const sim = new MatchSim({ ...AFL_SETTINGS, seed: 42 }); sim.start();
  sim.state.phase = 'live';
  Object.assign(sim.state.ball, { mode: 'loose', holderId: null, x: -50, y: 5, z: 0, vx: 30, vy: 14, vz: 0 });
  const team = sim.state.players.filter(p => p.team === 0 && !p.onBench);
  for (const p of team) { p.x = -50; p.z = 0; }
  team[0].x = 25; team[1].x = 20;
  const plan = new TeamPlan();
  const jobs = plan.update(sim.state, 1 / 60);
  expect(jobs.get(team[0].id)?.kind).toBe('contest');
  expect(jobs.get(team[0].id)!.x).toBeGreaterThan(25);
  const intent = aiIntentFor(team[0], { state: sim.state, jobs, difficulty: 'afl', possessingTeam: null, carrierId: null, liveTime: 1, rng: () => 0.5 });
  expect(intent.moveX).toBeGreaterThan(0); // landing is ahead; current ball is 75m behind
});
