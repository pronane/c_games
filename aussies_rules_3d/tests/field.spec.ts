import { describe, expect, it } from 'vitest';
import {
  boundaryCrossing,
  boundaryRadiusAt,
  betweenArcs,
  clampInside,
  inCentreCircle,
  inCentreSquare,
  inGoalSquare,
  insideAttackArc,
  isOutOfBounds,
  metresInside,
  scoreAtCrossing,
} from '../src/rules/field';
import { FIELD } from '../src/rules/types';

describe('field geometry (MCG-scale oval)', () => {
  it('the centre of the ground is inside the boundary', () => {
    expect(isOutOfBounds(0, 0)).toBe(false);
    expect(metresInside(0, 0)).toBeGreaterThan(50);
  });

  it('points beyond the boundary semi-axes are out of bounds', () => {
    expect(isOutOfBounds(FIELD.boundaryA + 1, 0)).toBe(true);
    expect(isOutOfBounds(0, FIELD.boundaryB + 1)).toBe(true);
  });

  it('the whole ball must be over the line: half-over is still in play', () => {
    // a ball whose centre is just inside is in play
    expect(isOutOfBounds(FIELD.boundaryA - 0.05, 0, 0.15)).toBe(false);
  });

  it('boundary radius grows between the axes (superellipse)', () => {
    const r0 = boundaryRadiusAt(0);
    const r45 = boundaryRadiusAt(Math.PI / 4);
    expect(r0).toBeCloseTo(FIELD.boundaryA, 1);
    expect(r45).toBeGreaterThan(r0 * 0.8);
  });

  it('goal lines sit inside the boundary, leaving room for behinds', () => {
    expect(FIELD.goalLineX).toBeLessThan(FIELD.boundaryA);
    expect(FIELD.behindPostHalf).toBeLessThan(FIELD.boundaryB);
  });

  it('goal squares are 9 m deep from the goal line and goal-post wide', () => {
    // team 0 defends the -x end, team 1 defends the +x end
    expect(inGoalSquare(-FIELD.goalLineX + 5, 0, 0)).toBe(true);
    expect(inGoalSquare(-FIELD.goalLineX + 12, 0, 0)).toBe(false);
    expect(inGoalSquare(-FIELD.goalLineX + 5, FIELD.goalPostHalf + 1, 0)).toBe(false);
    expect(inGoalSquare(FIELD.goalLineX - 5, 0, 1)).toBe(true);
    expect(inGoalSquare(-FIELD.goalLineX + 5, 0, 1)).toBe(false);
  });

  it('centre square is 50 m x 50 m and centre circle radius 10 m', () => {
    expect(inCentreSquare(24, 24)).toBe(true);
    expect(inCentreSquare(26, 0)).toBe(false);
    expect(inCentreCircle(9, 0)).toBe(true);
    expect(inCentreCircle(11, 0)).toBe(false);
  });

  it('50 m arcs are 50 m from the goal line centre', () => {
    expect(insideAttackArc(FIELD.goalLineX - 40, 0, 0)).toBe(true);
    expect(insideAttackArc(FIELD.goalLineX - 51, 0, 0)).toBe(false);
    expect(insideAttackArc(-FIELD.goalLineX + 40, 0, 1)).toBe(true);
  });

  it('betweenArcs is the corridor outside both 50 m arcs (2026 lasso zone)', () => {
    expect(betweenArcs(0)).toBe(true);
    expect(betweenArcs(FIELD.goalLineX - FIELD.arcRadius - 1)).toBe(true);
    expect(betweenArcs(FIELD.goalLineX - FIELD.arcRadius + 1)).toBe(false);
  });

  it('scoreAtCrossing classifies goal/behind gaps', () => {
    expect(scoreAtCrossing(FIELD.goalLineX, 0)).toEqual({ kind: 'goal', team: 0 });
    expect(scoreAtCrossing(FIELD.goalLineX, 6)).toEqual({ kind: 'behind', team: 0 });
    expect(scoreAtCrossing(FIELD.goalLineX, 12)).toBeNull();
    expect(scoreAtCrossing(-FIELD.goalLineX, -2)).toEqual({ kind: 'goal', team: 1 });
  });

  it('boundaryCrossing interpolates the exact crossing point', () => {
    const c = boundaryCrossing(80, 0, 120, 0);
    expect(c.x).toBeCloseTo(FIELD.boundaryA, 0);
    expect(Math.abs(c.z)).toBeLessThan(0.5);
  });

  it('clampInside keeps restart spots on the field', () => {
    const c = clampInside(200, 0);
    expect(isOutOfBounds(c.x, c.z)).toBe(false);
  });
});
