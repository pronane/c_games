import { describe, expect, it } from 'vitest';
import { MatchSim, emptyHumanIntent } from '../src/sim/match';
import { AFL_SETTINGS, MatchSettings, totalPoints } from '../src/rules/types';

const FAST: MatchSettings = { ...AFL_SETTINGS, quarterSeconds: 20, seed: 11 };

describe('match simulation smoke tests', () => {
  it('runs a full quarter of play without crashing and produces footy events', () => {
    const sim = new MatchSim(FAST, 'afl', 0);
    sim.start();
    const counts = new Map<string, number>();
    for (let i = 0; i < 20 * 60; i++) {
      const events = sim.update(1 / 60, emptyHumanIntent());
      for (const e of events) {
        counts.set(e.type, (counts.get(e.type) ?? 0) + 1);
      }
    }
    // the sim should have seen restarts and disposals
    expect((counts.get('ballUp') ?? 0) + (counts.get('throwIn') ?? 0) + (counts.get('centreBallUp') ?? 0)).toBeGreaterThan(0);
  });

  it('records kick and handball disposals as stat events', () => {
    const sim = new MatchSim(FAST, 'afl', 0);
    sim.start();
    let kicks = 0;
    let handballs = 0;
    for (let i = 0; i < 30 * 60; i++) {
      for (const e of sim.update(1 / 60, emptyHumanIntent())) {
        if (e.type === 'stat' && e.text === 'kick') kicks++;
        if (e.type === 'stat' && e.text === 'handball') handballs++;
      }
    }
    expect(kicks + handballs).toBeGreaterThan(0);
  });

  it('players stay inside the field boundary', () => {
    const sim = new MatchSim(FAST, 'club', 0);
    sim.start();
    for (let i = 0; i < 30 * 60; i++) {
      sim.update(1 / 60, emptyHumanIntent());
    }
    for (const p of sim.state.players) {
      expect(Math.abs(p.x)).toBeLessThan(95);
      expect(Math.abs(p.z)).toBeLessThan(85);
    }
  });

  it('the ball is always held by someone or loose/dead', () => {
    const sim = new MatchSim(FAST, 'afl', 0);
    sim.start();
    for (let i = 0; i < 30 * 60; i++) {
      sim.update(1 / 60, emptyHumanIntent());
      const b = sim.state.ball;
      expect(['held', 'loose', 'heldUmpire', 'dead']).toContain(b.mode);
      if (b.mode === 'held') {
        expect(b.holderId).not.toBeNull();
      }
    }
  });

  it('scores only move via goals and behinds', () => {
    const sim = new MatchSim(FAST, 'afl', 0);
    sim.start();
    for (let i = 0; i < 60 * 60; i++) {
      sim.update(1 / 60, emptyHumanIntent());
    }
    for (const s of sim.state.scores) {
      expect(s.goals).toBeGreaterThanOrEqual(0);
      expect(s.behinds).toBeGreaterThanOrEqual(0);
    }
    const pts = totalPoints(sim.state.scores[0]) + totalPoints(sim.state.scores[1]);
    expect(pts).toBe(sim.state.scores[0].goals * 6 + sim.state.scores[0].behinds +
      sim.state.scores[1].goals * 6 + sim.state.scores[1].behinds);
  });

  it('the human-controlled player can move and dispose of the ball', () => {
    const sim = new MatchSim(FAST, 'afl', 0);
    sim.start();
    // fast-forward until the controlled player has the ball
    let gotBall = false;
    for (let i = 0; i < 60 * 90 && !gotBall; i++) {
      const intent = emptyHumanIntent();
      // run toward the ball
      const me = sim.controlled();
      const b = sim.state.ball;
      if (me && b.mode === 'loose') {
        intent.moveX = Math.sign(b.x - me.x);
        intent.moveZ = Math.sign(b.z - me.z);
        intent.sprint = true;
      }
      sim.update(1 / 60, intent);
      const me2 = sim.controlled();
      gotBall = !!me2 && sim.state.ball.holderId === me2.id;
    }
    expect(gotBall).toBe(true);

    // kick it
    const intent = emptyHumanIntent();
    intent.kickHeld = true;
    sim.update(1 / 60, intent);
    intent.kickHeld = true;
    sim.update(0.3, intent);
    intent.kickHeld = false;
    intent.kickReleased = true;
    sim.update(1 / 60, intent);
    expect(sim.state.ball.mode).not.toBe('held');
  });

  it('is deterministic for a given seed', () => {
    const run = () => {
      const sim = new MatchSim({ ...FAST, seed: 5 }, 'afl', 0);
      sim.start();
      for (let i = 0; i < 45 * 60; i++) sim.update(1 / 60, emptyHumanIntent());
      return JSON.stringify([sim.state.scores, sim.state.ball.x.toFixed(1), sim.state.clock.quarter]);
    };
    expect(run()).toBe(run());
  });
});
