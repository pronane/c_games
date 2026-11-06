/**
 * The laws of Australian football (2026 Laws of the Game), as pure functions.
 *
 * Every function here is deterministic and side-effect free so the test suite
 * can verify each law in isolation. `engine.ts` wires them into live play.
 */
import {
  BallState,
  FIELD,
  FreeKick,
  FreeKickReason,
  MatchScore,
  PlayerState,
  TeamId,
  totalPoints,
} from './types';
import {
  attackGoalX,
  betweenArcs,
  clampInside,
  defendGoalX,
  inGoalSquare,
  isOutOfBounds,
  scoreAtCrossing,
} from './field';

// --------------------------------------------------------------------------- #
//  Scoring  (Law 1.5)
// --------------------------------------------------------------------------- #

export type ScoringOutcome =
  | { kind: 'goal'; team: TeamId; points: 6 }
  | { kind: 'behind'; team: TeamId; points: 1 }
  | { kind: 'goalPost'; behindTeam: TeamId } // ball hit a goal post → behind
  | { kind: 'behindPostOnFull'; freeKickTeam: TeamId } // hit behind post on the full
  | { kind: 'behindPostBounced' } // no score, throw-in at the post
  | { kind: 'none' };

/**
 * What happens when the ball reaches the goal line.
 *
 * - Kicked (or forced) through the two tall posts untouched → goal (6).
 *   The kicking team is the team that scored, regardless of who kicked it
 *   (a rushed/forced goal by the defender counts for the attackers).
 * - Between goal and behind posts, over the behind line, touching a goal
 *   post, or touched in flight → behind (1).
 * - Carried or handballed over the goal line by the attacking team → behind.
 * - A defender deliberately forcing the ball over their own goal line →
 *   behind + a free kick to the attackers (deliberate rushed behind).
 * - Ball hits a behind post on the full → out on the full, free kick to the
 *   opposition from beside the post. If it bounced first → throw-in, no score.
 */
export function scoreLineOutcome(
  ball: BallState,
  crossingX: number,
  crossingZ: number,
  kickedByTeam: TeamId | null,
  deliberateRush: boolean
  ): ScoringOutcome {
  void kickedByTeam;
  void deliberateRush; // the free kick for a deliberate rush is added by the engine
  const endTeam: TeamId = crossingX > 0 ? 0 : 1;
  const az = Math.abs(crossingZ);
  // Post strikes are classified first (posts sit on the goal line).
  if (Math.abs(az - FIELD.goalPostHalf) < 0.3) {
    return { kind: 'goalPost', behindTeam: endTeam };
  }
  if (Math.abs(az - FIELD.behindPostHalf) < 0.3) {
    return ball.bounced
      ? { kind: 'behindPostBounced' }
      : { kind: 'behindPostOnFull', freeKickTeam: endTeam === 0 ? 1 : 0 };
  }
  const at = scoreAtCrossing(crossingX, crossingZ);
  if (!at) return { kind: 'none' };

  if (at.kind === 'goal') {
    // Touched in flight, or not kicked (carried/handballed over) → behind.
    // A deliberate rushed goal by the defence still counts for the attackers.
    if (ball.touched || ball.lastDisposal !== 'kick') {
      return { kind: 'behind', team: endTeam, points: 1 };
    }
    return { kind: 'goal', team: endTeam, points: 6 };
  }

  // behind posts gap
  return { kind: 'behind', team: endTeam, points: 1 };
}

export function applyScore(scores: [MatchScore, MatchScore], outcome: ScoringOutcome): void {
  if (outcome.kind === 'goal') scores[outcome.team].goals += 1;
  else if (outcome.kind === 'behind') scores[outcome.team].behinds += 1;
  else if (outcome.kind === 'goalPost') scores[outcome.behindTeam].behinds += 1;
}

export function margin(scores: [MatchScore, MatchScore]): number {
  return totalPoints(scores[0]) - totalPoints(scores[1]);
}

// --------------------------------------------------------------------------- #
//  Marks  (Law 1.7 / 5.9)
// --------------------------------------------------------------------------- #

export type MarkDecision =
  | { kind: 'mark'; team: TeamId; playerId: number }
  | { kind: 'playOn'; reason: 'short' | 'touched' | 'bounced' | 'notCaught' };

/**
 * A mark: clean catch from a kick that travelled at least 15 m in the air
 * without being touched by anyone and without touching the ground.
 */
export function decideMark(
  ball: BallState,
  catcher: PlayerState
): MarkDecision {
  if (ball.mode !== 'held') return { kind: 'playOn', reason: 'notCaught' };
  if (ball.holderId !== catcher.id) return { kind: 'playOn', reason: 'notCaught' };
  if (ball.lastDisposal !== 'kick') return { kind: 'playOn', reason: 'notCaught' };
  if (ball.bounced) return { kind: 'playOn', reason: 'bounced' };
  if (ball.touched) return { kind: 'playOn', reason: 'touched' };
  if (ball.kickDistance < FIELD.markMinDistance) return { kind: 'playOn', reason: 'short' };
  return { kind: 'mark', team: catcher.team, playerId: catcher.id };
}

// --------------------------------------------------------------------------- #
//  Tackling & holding the ball  (Law 1.8)
// --------------------------------------------------------------------------- #

export type TackleDecision =
  | { kind: 'holdingTheBall'; againstId: number; toTeam: TeamId }
  | { kind: 'noPriorBallUp' }
  | { kind: 'legalTacklePlayOn' } // ball spilled free, play continues
  | { kind: 'highTackle'; againstId: number; toTeam: TeamId }
  | { kind: 'pushInTheBack'; againstId: number; toTeam: TeamId }
  | { kind: 'incorrectDisposal'; againstId: number; toTeam: TeamId };

export interface TackleContext {
  /** Tackled player had a prior opportunity (incl. shrug/fend, 2026 law). */
  priorOpportunity: boolean;
  /** Contact above the shoulders. */
  highContact: boolean;
  /** Contact in the back (push in the back). */
  backContact: boolean;
  /** Player disposed of it illegally (throw / dropped in the tackle). */
  incorrectDisposal: boolean;
  /** Ball came free immediately and the player attempted to dispose. */
  attemptedDisposal: boolean;
  ballSpilledFree: boolean;
}

/**
 * The most argued-about law in football.
 *
 * - Prior opportunity (including a shrug or fend) + tackled without a legal
 *   disposal → holding the ball.
 * - No prior opportunity → ball-up if locked up; play on if the ball spills
 *   free with a genuine disposal attempt.
 * - High contact / push in the back against the tackler.
 * - Throw or dropping it in the tackle → incorrect disposal.
 */
export function decideTackle(
  tackler: PlayerState,
  ballCarrier: PlayerState,
  ctx: TackleContext
): TackleDecision {
  const toTeam = tackler.team;
  if (ctx.highContact) return { kind: 'highTackle', againstId: tackler.id, toTeam: ballCarrier.team };
  if (ctx.backContact) return { kind: 'pushInTheBack', againstId: tackler.id, toTeam: ballCarrier.team };
  if (ctx.incorrectDisposal) {
    return { kind: 'incorrectDisposal', againstId: ballCarrier.id, toTeam };
  }
  if (ctx.priorOpportunity) {
    return { kind: 'holdingTheBall', againstId: ballCarrier.id, toTeam };
  }
  if (ctx.ballSpilledFree && ctx.attemptedDisposal) {
    return { kind: 'legalTacklePlayOn' };
  }
  return { kind: 'noPriorBallUp' };
}

// --------------------------------------------------------------------------- #
//  Running with the ball — the 15 m bounce law  (Law 1.7.3)
// --------------------------------------------------------------------------- #

/** Free kick against a player who runs more than 15 m without bouncing. */
export function decideRunTooFar(
  metresRunWithBall: number,
  hasBounced: boolean
): { kind: 'freeKick'; reason: 'runningTooFar' } | { kind: 'ok' } {
  if (!hasBounced && metresRunWithBall > FIELD.runBounceMetres) {
    return { kind: 'freeKick', reason: 'runningTooFar' };
  }
  return { kind: 'ok' };
}

// --------------------------------------------------------------------------- #
//  Out of bounds  (Law 12 — incl. the 2026 last-disposal "lasso" law)
// --------------------------------------------------------------------------- #

export type OutOfBoundsDecision =
  | { kind: 'outOnTheFull'; toTeam: TeamId; x: number; z: number }
  | { kind: 'lastDisposal'; toTeam: TeamId; x: number; z: number }
  | { kind: 'deliberate'; toTeam: TeamId; x: number; z: number }
  | { kind: 'throwIn'; x: number; z: number };

/**
 * 2026 out-of-bounds laws (`disposeTeam` = the team whose disposal took the
 * ball out; the free kick always goes to the other team):
 *
 * - Kicked (or handballed) out on the full, untouched → free kick to the
 *   opposition where it crossed (out on the full).
 * - LAST DISPOSAL between the 50 m arcs: a kick or handball that crosses the
 *   boundary untouched → free kick to the opposition ("lasso"). It becomes a
 *   throw-in if the ball was smothered or deflected off hands/feet.
 * - Inside the 50 m arcs the "insufficient intent" test remains: deliberate
 *   → free kick, otherwise throw-in.
 */
export function decideOutOfBounds(
  ball: BallState,
  crossX: number,
  crossZ: number,
  disposeTeam: TeamId | null,
  smotheredOrDeflected: boolean,
  deliberate: boolean
): OutOfBoundsDecision {
  const other = disposeTeam === null ? null : ((disposeTeam === 0 ? 1 : 0) as TeamId);

  // Out on the full: a kick that crossed without bouncing or being touched.
  if (ball.lastDisposal === 'kick' && !ball.bounced && !ball.touched && !smotheredOrDeflected && other !== null) {
    return { kind: 'outOnTheFull', toTeam: other, x: crossX, z: crossZ };
  }

  // 2026 last disposal law — only between the 50 m arcs.
  const kickedOrHandballed = ball.lastDisposal === 'kick' || ball.lastDisposal === 'handball';
  if (
    kickedOrHandballed &&
    !ball.touched &&
    !smotheredOrDeflected &&
    betweenArcs(crossX) &&
    other !== null
  ) {
    return { kind: 'lastDisposal', toTeam: other, x: crossX, z: crossZ };
  }

  // Inside the arcs: insufficient intent (deliberate) remains.
  if (deliberate && other !== null) {
    return { kind: 'deliberate', toTeam: other, x: crossX, z: crossZ };
  }
  return { kind: 'throwIn', x: crossX, z: crossZ };
}

// --------------------------------------------------------------------------- #
//  Kick-in after a behind  (Law 1.6)
// --------------------------------------------------------------------------- #

export type KickInDecision =
  | { kind: 'ok' }
  | { kind: 'freeKick'; reason: 'kickInNotCleared' | 'outOnTheFull'; toTeam: TeamId; x: number; z: number };

/**
 * Kick-in: taken by the defending team from within the goal square, within
 * 8 seconds (2026 law, aligned with set-kick time). The ball must be kicked.
 * If the kick-in goes out of bounds untouched after bouncing (or out on the
 * full), a free kick is awarded to the attacking team where it crossed.
 */
export function decideKickIn(
  ball: BallState,
  kickInTeam: TeamId,
  kickedFromX: number,
  kickedFromZ: number,
  crossX: number | null,
  crossZ: number | null,
  bouncedSinceKick: boolean,
  touchedSinceKick: boolean,
  timeTaken: number
): KickInDecision {
  const other = (kickInTeam === 0 ? 1 : 0) as TeamId;
  if (!inGoalSquare(kickedFromX, kickedFromZ, kickInTeam)) {
    return { kind: 'freeKick', reason: 'kickInNotCleared', toTeam: other, x: kickedFromX, z: kickedFromZ };
  }
  if (timeTaken > FIELD.restartSeconds) {
    return { kind: 'freeKick', reason: 'kickInNotCleared', toTeam: other, x: kickedFromX, z: kickedFromZ };
  }
  if (crossX !== null && crossZ !== null && !touchedSinceKick) {
    // out on the full straight from the kick-in, or bounce-then-out untouched
    return { kind: 'freeKick', reason: 'outOnTheFull', toTeam: other, x: crossX, z: crossZ };
  }
  void ball;
  void bouncedSinceKick;
  return { kind: 'ok' };
}

// --------------------------------------------------------------------------- #
//  Free kicks, marks & the 50 m penalty  (Law 1.8.4) / stand rule (2026)
// --------------------------------------------------------------------------- #

export function makeFreeKick(
  team: TeamId,
  takerId: number,
  x: number,
  z: number,
  reason: FreeKickReason,
  opts: Partial<FreeKick> = {}
): FreeKick {
  const spot = clampInside(x, z);
  return {
    team,
    takerId,
    x: spot.x,
    z: spot.z,
    reason,
    fiftyMetres: false,
    markX: spot.x,
    markZ: spot.z,
    shotClock: FIELD.restartSeconds,
    isMark: false,
    isSetShot: false,
    ...opts,
  };
}

/**
 * A 50 m penalty is awarded when an opponent interferes with the player
 * taking a mark or free kick (runs over the mark, holds them, fails to hand
 * the ball back, or moves within the protected area before the kick — the
 * 2026 "stand" rule: anyone inside 5 m must stand).
 */
export function applyFiftyMetrePenalty(fk: FreeKick): FreeKick {
  const goalX = attackGoalX(fk.team);
  const dir = Math.sign(goalX - fk.x) || 1;
  let nx = fk.x + dir * 50;
  // If already inside 50, the kick is brought to the top of the goal square.
  if (Math.abs(goalX - fk.x) < 50) {
    nx = goalX - dir * FIELD.goalSquareDepth;
  }
  const spot = clampInside(nx, fk.z);
  return {
    ...fk,
    x: spot.x,
    z: spot.z,
    fiftyMetres: true,
    isSetShot: Math.abs(goalX - spot.x) <= FIELD.arcRadius,
  };
}

/** Protected area: opponents within 5 m of the mark must stand (2026). */
export function mustStand(
  player: PlayerState,
  fk: FreeKick
): boolean {
  if (player.team === fk.team) return false;
  return Math.hypot(player.x - fk.markX, player.z - fk.markZ) <= FIELD.protectedAreaMetres;
}

/** The kick taker on a set shot: is it a shot for goal? */
export function isSetShot(fk: FreeKick): boolean {
  return Math.abs(attackGoalX(fk.team) - fk.x) <= FIELD.arcRadius;
}

// --------------------------------------------------------------------------- #
//  Centre ball-up laws  (2026: no centre bounce; ruck restrictions)
// --------------------------------------------------------------------------- #

/** 6-6-6 at centre ball-ups: 6 in each 50 m arc, 6 in the middle third. */
export interface SixSixSixCheck {
  ok: boolean;
  missingAttackArc: number;
  missingDefendArc: number;
  missingMiddle: number;
}

export function checkSixSixSix(players: PlayerState[], team: TeamId): SixSixSixCheck {
  const mine = players.filter((p) => p.team === team && !p.onBench);
  const gx = attackGoalX(team);
  const inAttack = mine.filter((p) => Math.hypot(p.x - gx, p.z) <= FIELD.arcRadius).length;
  const inDefend = mine.filter((p) => Math.hypot(p.x + gx, p.z) <= FIELD.arcRadius).length;
  const inMiddle = mine.length - inAttack - inDefend;
  return {
    ok: inAttack >= 6 && inDefend >= 6 && inMiddle >= 6,
    missingAttackArc: Math.max(0, 6 - inAttack),
    missingDefendArc: Math.max(0, 6 - inDefend),
    missingMiddle: Math.max(0, 6 - inMiddle),
  };
}

/** 2026: a competing ruck may not cross the centre circle line before contesting. */
export function ruckCrossedCentre(x: number, z: number, crossedSide: 'own' | 'opposition'): boolean {
  if (crossedSide === 'own') return false;
  return Math.hypot(x, z) > FIELD.centreCircleRadius;
}

// --------------------------------------------------------------------------- #
//  Clock  (Law 1.3 — 4 x 20 min + time on)
// --------------------------------------------------------------------------- #

export function formatClock(secondsRemaining: number): string {
  const s = Math.max(0, Math.ceil(secondsRemaining));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r.toString().padStart(2, '0')}`;
}

export function formatScore(scores: [MatchScore, MatchScore]): string {
  return `${totalPoints(scores[0])} — ${totalPoints(scores[1])}`;
}

/** Which direction the ball travels for a given phase of play. */
export function restartForTeam(team: TeamId, x: number, z: number): FreeKick {
  return makeFreeKick(team, -1, x, z, 'advantage');
}

export function isGoalSquareRestart(x: number, z: number, team: TeamId): boolean {
  return inGoalSquare(x, z, team);
}

export function goalLineXFor(team: TeamId): number {
  return defendGoalX(team);
}

export { isOutOfBounds };
