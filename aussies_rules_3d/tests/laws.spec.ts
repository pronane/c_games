import { describe, expect, it } from 'vitest';
import {
  applyFiftyMetrePenalty,
  checkSixSixSix,
  decideKickIn,
  decideMark,
  decideOutOfBounds,
  decideRunTooFar,
  decideTackle,
  makeFreeKick,
  mustStand,
} from '../src/rules/laws';
import { BallState, FIELD, PlayerState } from '../src/rules/types';

function ball(over: Partial<BallState> = {}): BallState {
  return {
    x: 0, y: 1, z: 0, vx: 0, vy: 0, vz: 0, spin: 0,
    mode: 'held', holderId: 1,
    kickedById: 2, kickedFromX: 40, kickedFromZ: 5,
    kickDistance: 35, kickedAt: 0,
    touched: false, bounced: false,
    lastDisposal: 'kick', handballedById: null,
    ...over,
  };
}

function player(id: number, team: 0 | 1, x = 0, z = 0): PlayerState {
  return {
    id, team, number: id, name: `P${id}`, role: 'midfielder',
    stats: { speed: 0.8, strength: 0.8, kicking: 0.8, marking: 0.8, tackling: 0.8, endurance: 0.8 },
    distanceRun: 0, stamina: 1, sprintRamp: 0, tackleCooldown: 0,
    x, z, y: 0, vx: 0, vy: 0, vz: 0, facing: 0, onBench: false,
  };
}

describe('marks (15 metres, untouched, on the full)', () => {
  it('a clean catch of a 15 m+ kick is a mark', () => {
    const d = decideMark(ball({ kickDistance: 22 }), player(1, 0));
    expect(d).toEqual({ kind: 'mark', team: 0, playerId: 1 });
  });

  it('exactly 15 metres counts (the law says "at least 15")', () => {
    const d = decideMark(ball({ kickDistance: 15 }), player(1, 0));
    expect(d.kind).toBe('mark');
  });

  it('a catch from a kick shorter than 15 m is play on', () => {
    const d = decideMark(ball({ kickDistance: 14.9 }), player(1, 0));
    expect(d).toEqual({ kind: 'playOn', reason: 'short' });
  });

  it('a touched kick cannot be marked', () => {
    const d = decideMark(ball({ touched: true }), player(1, 0));
    expect(d).toEqual({ kind: 'playOn', reason: 'touched' });
  });

  it('a ball that bounced cannot be marked', () => {
    const d = decideMark(ball({ bounced: true }), player(1, 0));
    expect(d).toEqual({ kind: 'playOn', reason: 'bounced' });
  });

  it('a handball cannot be marked', () => {
    const d = decideMark(ball({ lastDisposal: 'handball' }), player(1, 0));
    expect(d).toEqual({ kind: 'playOn', reason: 'notCaught' });
  });
});

describe('tackling & holding the ball', () => {
  const tackler = player(2, 1);
  const carrier = player(1, 0);

  it('prior opportunity + tackled without disposal = holding the ball', () => {
    const d = decideTackle(tackler, carrier, {
      priorOpportunity: true, highContact: false, backContact: false,
      incorrectDisposal: false, attemptedDisposal: false, ballSpilledFree: false,
    });
    expect(d).toEqual({ kind: 'holdingTheBall', againstId: 1, toTeam: 1 });
  });

  it('a shrug counts as prior opportunity (2026 law)', () => {
    const d = decideTackle(tackler, carrier, {
      priorOpportunity: true, highContact: false, backContact: false,
      incorrectDisposal: false, attemptedDisposal: false, ballSpilledFree: false,
    });
    expect(d.kind).toBe('holdingTheBall');
  });

  it('tackled immediately with no prior = ball-up', () => {
    const d = decideTackle(tackler, carrier, {
      priorOpportunity: false, highContact: false, backContact: false,
      incorrectDisposal: false, attemptedDisposal: false, ballSpilledFree: false,
    });
    expect(d).toEqual({ kind: 'noPriorBallUp' });
  });

  it('no prior but spills free with a disposal attempt = play on', () => {
    const d = decideTackle(tackler, carrier, {
      priorOpportunity: false, highContact: false, backContact: false,
      incorrectDisposal: false, attemptedDisposal: true, ballSpilledFree: true,
    });
    expect(d).toEqual({ kind: 'legalTacklePlayOn' });
  });

  it('high contact is a free kick against the tackler', () => {
    const d = decideTackle(tackler, carrier, {
      priorOpportunity: true, highContact: true, backContact: false,
      incorrectDisposal: false, attemptedDisposal: false, ballSpilledFree: false,
    });
    expect(d).toEqual({ kind: 'highTackle', againstId: 2, toTeam: 0 });
  });

  it('push in the back is a free kick against the tackler', () => {
    const d = decideTackle(tackler, carrier, {
      priorOpportunity: true, highContact: false, backContact: true,
      incorrectDisposal: false, attemptedDisposal: false, ballSpilledFree: false,
    });
    expect(d).toEqual({ kind: 'pushInTheBack', againstId: 2, toTeam: 0 });
  });

  it('throwing the ball / dropping it in the tackle is incorrect disposal', () => {
    const d = decideTackle(tackler, carrier, {
      priorOpportunity: true, highContact: false, backContact: false,
      incorrectDisposal: true, attemptedDisposal: false, ballSpilledFree: false,
    });
    expect(d).toEqual({ kind: 'incorrectDisposal', againstId: 1, toTeam: 1 });
  });
});

describe('running with the ball (the 15 m bounce law)', () => {
  it('running more than 15 m without bouncing is a free kick', () => {
    expect(decideRunTooFar(15.1, false).kind).toBe('freeKick');
    expect(decideRunTooFar(15.0, false).kind).toBe('ok');
    expect(decideRunTooFar(80, true).kind).toBe('ok');
  });
});

describe('out of bounds (2026 laws)', () => {
  const base = ball({ mode: 'loose', holderId: null });

  it('kicked out on the full (untouched) = free kick where it crossed', () => {
    const d = decideOutOfBounds(base, 20, 73.5, 1, false, false);
    expect(d.kind).toBe('outOnTheFull');
    if (d.kind === 'outOnTheFull') expect(d.toTeam).toBe(0);
  });

  it('last disposal between the arcs = free kick (2026 lasso law)', () => {
    const kickedBetweenArcs = decideOutOfBounds(
      ball({ mode: 'loose', holderId: null, bounced: true }),
      10, 73.5, 1, false, false
    );
    expect(kickedBetweenArcs.kind).toBe('lastDisposal');
    const handballedBetweenArcs = decideOutOfBounds(
      ball({ mode: 'loose', holderId: null, lastDisposal: 'handball', handballedById: 9, bounced: true }),
      10, 73.5, 1, false, false
    );
    expect(handballedBetweenArcs.kind).toBe('lastDisposal');
  });

  it('a smothered or deflected disposal that goes out is a throw-in', () => {
    const d = decideOutOfBounds(base, 10, 73.5, 1, true, false);
    expect(d.kind).toBe('throwIn');
  });

  it('a ball touched in flight that goes out is a throw-in', () => {
    const d = decideOutOfBounds(
      ball({ mode: 'loose', holderId: null, touched: true }), 10, 73.5, 1, false, false
    );
    expect(d.kind).toBe('throwIn');
  });

  it('inside the 50 m arcs the insufficient intent test remains', () => {
    const inArcX = FIELD.goalLineX - 30; // inside the arc of the +x goal
    const deliberate = decideOutOfBounds(
      ball({ mode: 'loose', holderId: null, lastDisposal: 'handball', bounced: true }),
      inArcX, 73.5, 1, false, true
    );
    expect(deliberate.kind).toBe('deliberate');
    const accidental = decideOutOfBounds(
      ball({ mode: 'loose', holderId: null, lastDisposal: 'handball', bounced: true }),
      inArcX, 73.5, 1, false, false
    );
    expect(accidental.kind).toBe('throwIn');
  });
});

describe('kick-in after a behind (8 seconds, from the goal square)', () => {
  const gx = FIELD.goalLineX; // team 1 defends this end

  it('a legal kick-in from the goal square is fine', () => {
    const d = decideKickIn(ball(), 1, gx - 4, 0, null, null, false, false, 2);
    expect(d).toEqual({ kind: 'ok' });
  });

  it('taking longer than 8 seconds is a free kick against', () => {
    const d = decideKickIn(ball(), 1, gx - 4, 0, null, null, false, false, 8.5);
    expect(d.kind).toBe('freeKick');
    if (d.kind === 'freeKick') {
      expect(d.reason).toBe('kickInNotCleared');
      expect(d.toTeam).toBe(0);
    }
  });

  it('a kick-in out on the full is a free kick to the attackers', () => {
    const d = decideKickIn(ball(), 1, gx - 4, 0, gx + 0.1, 40, false, false, 3);
    expect(d.kind).toBe('freeKick');
    if (d.kind === 'freeKick') expect(d.reason).toBe('outOnTheFull');
  });

  it('a kick-in must be taken from inside the goal square', () => {
    const d = decideKickIn(ball(), 1, gx - 20, 0, null, null, false, false, 2);
    expect(d.kind).toBe('freeKick');
  });
});

describe('50 m penalty & stand rule', () => {
  it('a 50 m penalty advances the mark 50 m toward goal', () => {
    const fk = makeFreeKick(0, 1, 0, 10, 'mark');
    const up = applyFiftyMetrePenalty(fk);
    expect(up.x).toBeCloseTo(50, 0);
    expect(up.fiftyMetres).toBe(true);
  });

  it('inside 50 the kick moves to the top of the goal square', () => {
    const fk = makeFreeKick(0, 1, 40, 0, 'mark');
    const up = applyFiftyMetrePenalty(fk);
    expect(up.x).toBeCloseTo(FIELD.goalLineX - FIELD.goalSquareDepth, 0);
  });

  it('opponents within 5 m of the mark must stand (2026 protected area)', () => {
    const fk = makeFreeKick(0, 1, 30, 0, 'mark');
    expect(mustStand(player(9, 1, 33, 0), fk)).toBe(true);
    expect(mustStand(player(9, 1, 40, 0), fk)).toBe(false);
    expect(mustStand(player(9, 0, 31, 0), fk)).toBe(false); // team-mate
  });
});

describe('6-6-6 at centre ball-ups (2026: no goal-square requirement)', () => {
  it('six in each arc and six in the middle satisfies the rule', () => {
    const players: PlayerState[] = [];
    const gx = FIELD.goalLineX;
    for (let i = 0; i < 6; i++) players.push(player(0 + i, 0, gx - 30, -20 + i * 8));
    for (let i = 0; i < 6; i++) players.push(player(10 + i, 0, -gx + 30, -20 + i * 8));
    for (let i = 0; i < 6; i++) players.push(player(20 + i, 0, 5, -20 + i * 8));
    const check = checkSixSixSix(players, 0);
    expect(check.ok).toBe(true);
  });

  it('a missing player in the attack arc is reported', () => {
    const players: PlayerState[] = [];
    const gx = FIELD.goalLineX;
    for (let i = 0; i < 5; i++) players.push(player(i, 0, gx - 30, i * 8));
    for (let i = 0; i < 6; i++) players.push(player(10 + i, 0, -gx + 30, i * 8));
    for (let i = 0; i < 7; i++) players.push(player(20 + i, 0, 5, i * 8));
    const check = checkSixSixSix(players, 0);
    expect(check.ok).toBe(false);
    expect(check.missingAttackArc).toBe(1);
  });
});
