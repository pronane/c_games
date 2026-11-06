import { describe, expect, it } from 'vitest';
import { RulesEngine, buildRoster } from '../src/rules/engine';
import { AFL_SETTINGS, FIELD, MatchSettings, totalPoints } from '../src/rules/types';
import { formatClock } from '../src/rules/laws';

const FAST: MatchSettings = { ...AFL_SETTINGS, quarterSeconds: 30, seed: 42 };

function started(): RulesEngine {
  const e = new RulesEngine(FAST);
  e.buildTeams();
  e.startMatch();
  return e;
}

describe('match clock (4 x 20 minutes + time on)', () => {
  it('AFL settings are exactly four 20-minute quarters', () => {
    expect(AFL_SETTINGS.quarters).toBe(4);
    expect(AFL_SETTINGS.quarterSeconds).toBe(20 * 60);
    expect(AFL_SETTINGS.interchange).toBe(5); // 2026: five on the bench
    expect(AFL_SETTINGS.rotationCap).toBe(75);
  });

  it('the clock only runs while the ball is live', () => {
    const e = started();
    expect(e.state.phase).toBe('centreBallUp');
    const before = e.state.clock.secondsRemaining;
    e.step(1);
    expect(e.state.clock.secondsRemaining).toBe(before); // stopped at the ball-up
    // complete the ball-up
    e.step(2);
    expect(e.state.phase).toBe('live');
    e.step(1);
    expect(e.state.clock.secondsRemaining).toBeCloseTo(before - 1, 1);
  });

  it('formats as m:ss', () => {
    expect(formatClock(20 * 60)).toBe('20:00');
    expect(formatClock(75)).toBe('1:15');
    expect(formatClock(0)).toBe('0:00');
  });

  it('ends the quarter at zero and starts the next one', () => {
    const e = started();
    e.step(2); // into live play
    e.step(31); // quarter expires
    expect(e.state.clock.quarter).toBe(1);
    expect(e.state.phase).toBe('quarterBreak');
    e.step(7); // break over
    expect(e.state.clock.quarter).toBe(2);
    expect(e.state.clock.secondsRemaining).toBe(30);
  });

  it('the match ends after the final siren', () => {
    const e = new RulesEngine({ ...FAST, quarters: 1 });
    e.buildTeams();
    e.startMatch();
    e.step(2);
    e.step(31);
    e.step(7);
    expect(e.state.phase).toBe('matchEnd');
  });
});

describe('possession & the laws in play', () => {
  it('giving a player the ball sets up a free kick after a mark', () => {
    const e = started();
    e.step(2);
    const kicker = e.state.players.find((p) => p.team === 0 && !p.onBench)!;
    const catcher = e.state.players.find((p) => p.team === 0 && p.id !== kicker.id && !p.onBench)!;
    catcher.x = 40;
    catcher.z = 10;
    e.giveBallTo(kicker.id);
    e.onKick(kicker.id);
    // simulate the kick travelling 25 m
    e.state.ball.kickDistance = 25;
    e.state.ball.lastDisposal = 'kick';
    e.onBallCaught(catcher.id);
    expect(e.state.phase).toBe('freeKick');
    expect(e.state.freeKick?.isMark).toBe(true);
    expect(e.state.freeKick?.takerId).toBe(catcher.id);
  });

  it('a short kick that is caught is not a mark', () => {
    const e = started();
    e.step(2);
    const kicker = e.state.players.find((p) => p.team === 0 && !p.onBench)!;
    const catcher = e.state.players.find((p) => p.team === 0 && p.id !== kicker.id && !p.onBench)!;
    e.giveBallTo(kicker.id);
    e.onKick(kicker.id);
    e.state.ball.kickDistance = 8;
    e.onBallCaught(catcher.id);
    expect(e.state.freeKick?.isMark ?? false).toBe(false);
    expect(e.state.ball.holderId).toBe(catcher.id); // just a pickup
  });

  it('running more than 15 m without bouncing concedes a free kick', () => {
    const e = started();
    e.step(2);
    const runner = e.state.players.find((p) => p.team === 0 && !p.onBench)!;
    e.giveBallTo(runner.id);
    e.onRunMetres(runner.id, 16);
    expect(e.state.phase).toBe('freeKick');
    expect(e.state.freeKick?.reason).toBe('runningTooFar');
    expect(e.state.freeKick?.team).toBe(1);
  });

  it('bouncing resets the 15 m count', () => {
    const e = started();
    e.step(2);
    const runner = e.state.players.find((p) => p.team === 0 && !p.onBench)!;
    e.giveBallTo(runner.id);
    e.onRunMetres(runner.id, 12);
    e.onBounce(runner.id);
    e.onRunMetres(runner.id, 12);
    expect(e.state.phase).toBe('live');
  });

  it('holding the ball is paid when tackled with prior opportunity', () => {
    const e = started();
    e.step(2);
    const carrier = e.state.players.find((p) => p.team === 0 && !p.onBench)!;
    const tackler = e.state.players.find((p) => p.team === 1 && !p.onBench)!;
    e.giveBallTo(carrier.id);
    e.step(1); // > 0.35 s of prior opportunity
    e.onTackle(tackler.id, carrier.id, {
      priorOpportunity: false, highContact: false, backContact: false,
      incorrectDisposal: false, attemptedDisposal: false, ballSpilledFree: false,
    });
    expect(e.state.freeKick?.reason).toBe('holdingTheBall');
    expect(e.state.freeKick?.team).toBe(1);
  });

  it('no prior opportunity in a tackle produces a ball-up', () => {
    const e = started();
    e.step(2);
    const carrier = e.state.players.find((p) => p.team === 0 && !p.onBench)!;
    const tackler = e.state.players.find((p) => p.team === 1 && !p.onBench)!;
    carrier.x = 12;
    carrier.z = 4;
    e.giveBallTo(carrier.id);
    e.onTackle(tackler.id, carrier.id, {
      priorOpportunity: false, highContact: false, backContact: false,
      incorrectDisposal: false, attemptedDisposal: false, ballSpilledFree: false,
    });
    expect(e.state.phase).toBe('ballUp');
    expect(Math.abs(e.state.restartX - 12)).toBeLessThan(3);
  });
});

describe('scores & restarts', () => {
  it('a goal scores 6 and restarts with a centre ball-up (2026: no bounce)', () => {
    const e = started();
    e.step(2);
    e.state.ball.lastDisposal = 'kick';
    e.state.ball.touched = false;
    e.onGoalLineCrossed(FIELD.goalLineX - 0.1, 0);
    expect(e.state.scores[0].goals).toBe(1);
    expect(totalPoints(e.state.scores[0])).toBe(6);
    expect(e.state.phase).toBe('scoreCelebration');
    e.step(3.5);
    expect(e.state.phase).toBe('centreBallUp');
  });

  it('a behind scores 1 and restarts with a kick-in from the goal square', () => {
    const e = started();
    e.step(2);
    e.state.ball.lastDisposal = 'kick';
    e.state.ball.touched = true; // touched through
    e.onGoalLineCrossed(FIELD.goalLineX - 0.1, 4);
    expect(e.state.scores[0].behinds).toBe(1);
    e.step(3.5);
    expect(e.state.phase).toBe('kickIn');
    expect(e.state.freeKick?.team).toBe(1); // defending team kicks in
  });

  it('out on the full gives a free kick to the opposition where it crossed', () => {
    const e = started();
    e.step(2);
    const kicker = e.state.players.find((p) => p.team === 0 && !p.onBench)!;
    e.state.ball.kickedById = kicker.id;
    e.state.ball.lastDisposal = 'kick';
    e.state.ball.touched = false;
    e.state.ball.bounced = false;
    e.onBoundaryCrossed(20, 70, { x: 21, z: 74 }, false, false);
    expect(e.state.phase).toBe('freeKick');
    expect(e.state.freeKick?.reason).toBe('outOnTheFull');
    expect(e.state.freeKick?.team).toBe(1);
  });

  it('a 50 m penalty is applied when the protected area is breached', () => {
    const e = started();
    e.step(2);
    const taker = e.state.players.find((p) => p.team === 0 && !p.onBench)!;
    taker.x = 0;
    taker.z = 0;
    e.awardFreeKick({
      team: 0, takerId: taker.id, x: 0, z: 0, reason: 'mark',
      fiftyMetres: false, markX: 0, markZ: 0, shotClock: 8,
      isMark: true, isSetShot: false,
    });
    const intruder = e.state.players.find((p) => p.team === 1 && !p.onBench)!;
    intruder.x = 3;
    intruder.z = 0;
    e.onProtectedAreaBreach(intruder.id);
    expect(e.state.freeKick?.fiftyMetres).toBe(true);
    expect(e.state.freeKick?.x).toBeCloseTo(50, 0);
  });
});

describe('rosters & teams', () => {
  it('each team has 18 on the ground plus the interchange bench', () => {
    const e = new RulesEngine(AFL_SETTINGS);
    e.buildTeams();
    const home = e.state.players.filter((p) => p.team === 0);
    expect(home.length).toBe(18 + AFL_SETTINGS.interchange);
    expect(home.filter((p) => p.onBench).length).toBe(AFL_SETTINGS.interchange);
  });

  it('rosters are deterministic for a given seed', () => {
    const a = buildRoster(0, 7, 5);
    const b = buildRoster(0, 7, 5);
    expect(a.map((r) => r.name)).toEqual(b.map((r) => r.name));
    const c = buildRoster(0, 8, 5);
    expect(a.map((r) => r.name)).not.toEqual(c.map((r) => r.name));
  });
});
