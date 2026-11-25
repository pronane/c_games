import { describe, it, expect } from 'vitest';
import { Vector3, PerspectiveCamera } from 'three';
import { angleDelta, playerModelYaw, stepLocomotion } from '../src/sim/locomotion';
import { ballPresentation } from '../src/render/ballReadability';
import { TeamPlan } from '../src/sim/teamPlan';
import { MatchSim, emptyHumanIntent } from '../src/sim/match';
import { captureIntent } from '../src/sim/captureScenario';
import { AFL_SETTINGS } from '../src/rules/types';
import { BroadcastCamera } from '../src/render/camera';

describe('gameplay recovery regressions', () => {
  it('maps the model -Z forward axis to sim facing in all quadrants', () => {
    for (const facing of [0, Math.PI / 2, Math.PI, -Math.PI / 2]) {
      const forward = new Vector3(0, 0, -1).applyAxisAngle(new Vector3(0, 1, 0), playerModelYaw(facing));
      expect(forward.x).toBeCloseTo(Math.cos(facing));
      expect(forward.z).toBeCloseTo(Math.sin(facing));
    }
  });
  it('bounds acceleration and turns before accelerating into a reversal', () => {
    const p = { vx: 8, vz: 0, facing: 0 };
    let slowest = 8;
    for (let i = 0; i < 180; i++) {
      const old = { ...p };
      stepLocomotion(p, -1, 0, 8, 1 / 60);
      expect(Math.hypot(p.vx - old.vx, p.vz - old.vz)).toBeLessThanOrEqual(12 / 60 + 1e-8);
      expect(Math.abs(angleDelta(p.facing, old.facing))).toBeLessThanOrEqual(7 / 60 + 1e-8);
      slowest = Math.min(slowest, Math.hypot(p.vx, p.vz));
    }
    expect(slowest).toBeLessThan(4);
    expect(p.vx).toBeLessThan(-6);
    expect(Math.abs(angleDelta(Math.PI, p.facing))).toBeLessThan(0.01);
  });
  it('stops without spinning and remains finite across timestep sizes', () => {
    for (const dt of [1 / 30, 1 / 60, 1 / 120]) {
      const p = { vx: 6, vz: 0, facing: 0 };
      for (let t = 0; t < 2; t += dt) stepLocomotion(p, 0, 0, 8, dt);
      expect(Math.hypot(p.vx, p.vz)).toBeLessThan(0.01);
      expect(p.facing).toBe(0);
    }
  });
  it('caps visual-only ball enlargement, preserving a locator at long distances', () => {
    for (const depth of [10, 40, 80, 200]) {
      const s = ballPresentation(depth, 46, 720);
      expect(s.scale).toBeGreaterThanOrEqual(1);
      expect(s.scale).toBeLessThanOrEqual(2.5);
      expect(s.locatorMetres).toBeGreaterThan(0);
    }
    expect(ballPresentation(40, 46, 720).minorPixels).toBeGreaterThanOrEqual(6 - 1e-8);
  });
  it('holds contest jobs and reserves distinct receiving lanes', () => {
    const sim = new MatchSim({ ...AFL_SETTINGS, seed: 42 }); sim.start();
    sim.state.phase = 'live';
    const plan = new TeamPlan();
    const jobs = plan.update(sim.state, 1 / 60);
    for (const team of [0, 1]) {
      const own = [...jobs].filter(([id]) => sim.state.players.find(p => p.id === id)!.team === team);
      expect(own.filter(([, job]) => job.kind === 'contest')).toHaveLength(2);
      const receivers = own.filter(([, job]) => ['short', 'outlet'].includes(job.kind));
      expect(receivers).toHaveLength(2);
      expect(receivers[0][1].z).not.toBe(receivers[1][1].z);
    }
    expect(plan.update(sim.state, 0.1)).toBe(jobs);
    sim.state.ball.holderId = sim.state.players[0].id;
    sim.state.ball.mode = 'held';
    expect(plan.update(sim.state, 0.1)).not.toBe(jobs);
  });
  it('does not zoom out to a distant selected player', () => {
    const sim = new MatchSim({ ...AFL_SETTINGS, seed: 42 }); sim.start();
    const cameras = [new PerspectiveCamera(46, 16 / 9, 0.5, 1600), new PerspectiveCamera(46, 16 / 9, 0.5, 1600)];
    const rigs = cameras.map(c => new BroadcastCamera(c));
    for (let i = 0; i < 120; i++) {
      rigs[0].update(1 / 60, sim.state);
      rigs[1].update(1 / 60, sim.state, { x: 100, y: 1, z: 80 });
    }
    expect(cameras[0].position.distanceTo(cameras[1].position)).toBeLessThan(1e-8);
    expect(rigs[1].diagnostics.playerExcluded).toBe(true);
  });
  it('does not tackle during a protected restart, including human button presses', () => {
    const sim = new MatchSim({ ...AFL_SETTINGS, seed: 42 }); sim.start();
    const player = sim.state.players.find(p => p.id === sim.controlledId)!;
    const carrier = sim.state.players.find(p => p.team !== player.team)!;
    sim.engine.giveBallTo(carrier.id);
    sim.state.phase = 'freeKick';
    player.x = carrier.x; player.z = carrier.z;
    const input = emptyHumanIntent(); input.tackle = true;
    sim.update(1 / 60, input);
    expect(sim.diagnostics.tackles).toBe(0);
  });
  it('replays the scripted input trace deterministically, including event reasons', () => {
    const run = () => {
      const sim = new MatchSim({ ...AFL_SETTINGS, seed: 123, quarterSeconds: 120 }); sim.start();
      const events: string[] = [];
      for (let tick = 0; tick < 1800; tick++) {
        for (const event of sim.update(1 / 60, captureIntent(tick))) events.push(`${tick}:${event.type}:${event.text ?? ''}`);
      }
      // Standing wrap actions must not invent illegal high/back-contact geometry.
      expect(sim.diagnostics.freesByReason.highTackle ?? 0).toBe(0);
      expect(sim.diagnostics.freesByReason.pushInTheBack ?? 0).toBe(0);
      return JSON.stringify([sim.state.ball, sim.state.scores, events, sim.diagnostics]);
    };
    expect(run()).toBe(run());
  });
});
