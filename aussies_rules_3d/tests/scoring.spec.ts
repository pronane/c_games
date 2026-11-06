import { describe, expect, it } from 'vitest';
import { applyScore, margin, scoreLineOutcome } from '../src/rules/laws';
import { FIELD, MatchScore, BallState } from '../src/rules/types';

function ball(over: Partial<BallState> = {}): BallState {
  return {
    x: 0, y: 0, z: 0, vx: 0, vy: 0, vz: 0, spin: 0,
    mode: 'loose', holderId: null,
    kickedById: 1, kickedFromX: 50, kickedFromZ: 0,
    kickDistance: 40, kickedAt: 0,
    touched: false, bounced: false,
    lastDisposal: 'kick', handballedById: null,
    ...over,
  };
}

describe('scoring laws (Law 1.5)', () => {
  it('a kicked goal through the middle posts is 6 points', () => {
    const out = scoreLineOutcome(ball(), FIELD.goalLineX, 0, 0, false);
    expect(out).toEqual({ kind: 'goal', team: 0, points: 6 });
  });

  it('a goal at the other end scores for the team attacking that end', () => {
    const out = scoreLineOutcome(ball(), -FIELD.goalLineX, 1, 1, false);
    expect(out).toEqual({ kind: 'goal', team: 1, points: 6 });
  });

  it('a ball touched in flight through the middle is only a behind', () => {
    const out = scoreLineOutcome(ball({ touched: true }), FIELD.goalLineX, 0, 0, false);
    expect(out).toEqual({ kind: 'behind', team: 0, points: 1 });
  });

  it('a handballed or carried ball over the goal line is a behind', () => {
    const out = scoreLineOutcome(
      ball({ lastDisposal: 'handball' }), FIELD.goalLineX, 0, 0, false
    );
    expect(out).toEqual({ kind: 'behind', team: 0, points: 1 });
  });

  it('through the outer gap (goal post to behind post) is a behind', () => {
    const out = scoreLineOutcome(ball(), FIELD.goalLineX, 6.4, 0, false);
    expect(out).toEqual({ kind: 'behind', team: 0, points: 1 });
  });

  it('hitting the goal post is always a behind', () => {
    const out = scoreLineOutcome(ball(), FIELD.goalLineX, FIELD.goalPostHalf, 0, false);
    expect(out).toEqual({ kind: 'goalPost', behindTeam: 0 });
  });

  it('hitting the behind post on the full is out on the full, no score', () => {
    const out = scoreLineOutcome(ball(), FIELD.goalLineX, FIELD.behindPostHalf, 0, false);
    expect(out).toEqual({ kind: 'behindPostOnFull', freeKickTeam: 1 });
  });

  it('hitting the behind post after a bounce is a throw-in, no score', () => {
    const out = scoreLineOutcome(
      ball({ bounced: true }), FIELD.goalLineX, FIELD.behindPostHalf, 0, false
    );
    expect(out).toEqual({ kind: 'behindPostBounced' });
  });

  it('a defender rushing a behind still concedes one point', () => {
    // team-1 defender (201) forces it over the goal line team 1 defends (+x)
    const out = scoreLineOutcome(
      ball({ lastDisposal: 'handball', handballedById: 201 }),
      FIELD.goalLineX, 0, 1, true
    );
    expect(out).toEqual({ kind: 'behind', team: 0, points: 1 });
  });

  it('scores accumulate as goals.behinds and total points', () => {
    const scores: [MatchScore, MatchScore] = [
      { goals: 0, behinds: 0 },
      { goals: 0, behinds: 0 },
    ];
    applyScore(scores, { kind: 'goal', team: 0, points: 6 });
    applyScore(scores, { kind: 'behind', team: 0, points: 1 });
    applyScore(scores, { kind: 'goal', team: 1, points: 6 });
    applyScore(scores, { kind: 'goal', team: 1, points: 6 });
    expect(scores[0]).toEqual({ goals: 1, behinds: 1 });
    expect(scores[1]).toEqual({ goals: 2, behinds: 0 });
    expect(margin(scores)).toBe(7 - 12);
  });
});
