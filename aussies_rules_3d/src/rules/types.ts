/**
 * Aussie Rules 3D — core types for the laws engine.
 *
 * The rules engine is pure TypeScript (no rendering, no I/O) so it can be
 * tested headlessly and reused by the renderer, the AI and the test suite.
 * Laws implemented here follow the 2026 Laws of Australian Football.
 */

export type TeamId = 0 | 1; // 0 = home (attacks +x), 1 = away (attacks -x)

export type PlayerRole =
  | 'fullback'
  | 'keyDefender'
  | 'halfBack'
  | 'midfielder'
  | 'ruck'
  | 'halfForward'
  | 'keyForward'
  | 'fullForward';

export interface PlayerStats {
  speed: number; // 0..1
  strength: number;
  kicking: number;
  marking: number;
  tackling: number;
  endurance: number;
}

export interface PlayerState {
  id: number;
  team: TeamId;
  number: number;
  name: string;
  role: PlayerRole;
  stats: PlayerStats;
  /** Metres run since last break — used for fatigue and interchange. */
  distanceRun: number;
  stamina: number; // 0..1
  /** 0..1 sprint build-up — ramps while sprinting, decays otherwise. */
  sprintRamp: number;
  /** Seconds until this player may legally attempt another tackle. */
  tackleCooldown: number;
  /** Position on the field (x = goal-to-goal axis, z = wing axis), metres. */
  x: number;
  z: number;
  /** Height above ground (marks, jumps), metres. */
  y: number;
  vx: number;
  vy: number;
  vz: number;
  facing: number; // radians, 0 = +x
  onBench: boolean;
}

export type BallMode =
  | 'held' // carried by a player
  | 'loose' // free flight / bouncing
  | 'heldUmpire' // umpire has it (ball-up, restarts)
  | 'dead'; // goal/behind scored, between plays

export interface BallState {
  x: number;
  y: number;
  z: number;
  vx: number;
  vy: number;
  vz: number;
  spin: number;
  mode: BallMode;
  /** Player currently holding the ball (when mode === 'held'). */
  holderId: number | null;
  /** Set when the ball is live from a kick (for marks / out on the full). */
  kickedById: number | null;
  kickedFromX: number;
  kickedFromZ: number;
  kickDistance: number; // air distance travelled since kick (untouched)
  kickedAt: number; // match time of the kick (s)
  touched: boolean; // touched in flight (cancels mark, changes OOB call)
  bounced: boolean; // hit the ground since the kick
  lastDisposal: 'kick' | 'handball' | 'none'; // for the 2026 last-disposal law
  handballedById: number | null;
}

export type PlayPhase =
  | 'preMatch'
  | 'quarterBreak'
  | 'centreBallUp' // umpire throwing ball up at centre (2026: no bounce)
  | 'ballUp' // around-the-ground stoppage restart
  | 'throwIn' // boundary throw-in
  | 'freeKick' // player about to take a free kick / mark
  | 'kickIn' // after a behind
  | 'live' // general play
  | 'scoreCelebration'
  | 'quarterEnd'
  | 'matchEnd';

export interface FreeKick {
  team: TeamId;
  takerId: number;
  x: number;
  z: number;
  reason: FreeKickReason;
  /** Set for 50m penalties: kick is advanced 50m toward goal. */
  fiftyMetres: boolean;
  /** The "mark" spot the nearest opponent must stand at. */
  markX: number;
  markZ: number;
  /** Seconds the taker has to bring the ball back into play (8s, 2026). */
  shotClock: number;
  isMark: boolean;
  isSetShot: boolean; // kick for goal situation (inside 50)
}

export type FreeKickReason =
  | 'mark'
  | 'holdingTheBall'
  | 'runningTooFar'
  | 'highTackle'
  | 'pushInTheBack'
  | 'holdingTheMan'
  | 'throwing'
  | 'trip'
  | 'kickInDanger'
  | 'charge'
  | 'outOnTheFull'
  | 'lastDisposalOOB'
  | 'deliberateOOB'
  | 'deliberateRushedBehind'
  | 'interferenceAfterMark' // 50m
  | 'protectedArea' // stand rule breach → 50m
  | 'thirdManUp'
  | 'ruckCrossedCentre'
  | 'kickInNotCleared'
  | 'advantage';

export interface MatchScore {
  goals: number;
  behinds: number;
}

export function totalPoints(s: MatchScore): number {
  return s.goals * 6 + s.behinds;
}

export function scoreString(s: MatchScore): string {
  return `${s.goals}.${s.behinds} (${totalPoints(s)})`;
}

export interface MatchSettings {
  /** Quarter length in seconds of playing time (AFL: 20 * 60). */
  quarterSeconds: number;
  /** Number of quarters (AFL: 4). */
  quarters: number;
  /** Interchange players per team (AFL 2026: 5). */
  interchange: number;
  /** Maximum interchange rotations per team (AFL: 75). */
  rotationCap: number;
  /** Seed for deterministic sims/tests. */
  seed: number;
  /** Difficulty scales AI reaction and accuracy. */
  difficulty: 'rookie' | 'club' | 'afl';
}

export const AFL_SETTINGS: MatchSettings = {
  quarterSeconds: 20 * 60,
  quarters: 4,
  interchange: 5,
  rotationCap: 75,
  seed: 1,
  difficulty: 'afl',
};

export interface MatchClock {
  quarter: number; // 1..4
  /** Seconds remaining in the quarter of playing time. */
  secondsRemaining: number;
  /** True while the ball is live and the clock runs. */
  running: boolean;
  /** Accumulated stoppage time (displayed as "time on"). */
  timeOn: number;
}

export interface MatchState {
  settings: MatchSettings;
  clock: MatchClock;
  scores: [MatchScore, MatchScore];
  ball: BallState;
  players: PlayerState[];
  phase: PlayPhase;
  freeKick: FreeKick | null;
  /** Where the next restart (ball-up / throw-in / kick-in) happens. */
  restartX: number;
  restartZ: number;
  /** Rucks nominated for the next ball-up. */
  nominatedRucks: [number | null, number | null];
  /** Interchange rotations used. */
  rotations: [number, number];
  /** Last event list drained by the UI/audio layer each frame. */
  events: MatchEvent[];
  /** Winner at match end (null = draw or in progress). */
  winner: TeamId | null;
  /** Kick-in deadline (match-clock seconds), 8s rule. */
  setShotDeadline: number;
}

export type MatchEventType =
  | 'goal'
  | 'behind'
  | 'mark'
  | 'freeKick'
  | 'fiftyMetres'
  | 'ballUp'
  | 'throwIn'
  | 'kickIn'
  | 'centreBallUp'
  | 'quarterEnd'
  | 'matchEnd'
  | 'siren'
  | 'hold'
  | 'tackle'
  | 'smother'
  | 'touch'
  | 'playOn'
  | 'outOnTheFull'
  | 'lastDisposal'
  | 'stat';

export interface MatchEvent {
  type: MatchEventType;
  team?: TeamId;
  playerId?: number;
  x?: number;
  z?: number;
  text?: string;
  points?: number;
}

/** Field geometry constants (metres). MCG-scale oval. */
export const FIELD = {
  /** Superellipse exponent for the boundary shape. */
  shapeN: 2.4,
  /** Boundary semi-axes: x = goal-to-goal, z = wing to wing. */
  boundaryA: 85.5,
  boundaryB: 73.0,
  /** Goal line distance from centre along x. */
  goalLineX: 69.0,
  /** Half-distance between the goal posts (6.4 m apart). */
  goalPostHalf: 3.2,
  /** Behind posts sit 6.4 m outside the goal posts. */
  behindPostHalf: 9.6,
  /** Goal square depth (9 m) and half width (= goal post half). */
  goalSquareDepth: 9.0,
  /** 50 metre arc radius (from the centre of the goal line). */
  arcRadius: 50.0,
  /** Centre square is 50 m x 50 m. */
  centreSquareHalf: 25.0,
  /** Centre circle radius (ruck line at centre ball-ups). */
  centreCircleRadius: 10.0,
  /** Kick must travel at least this far untouched to be a mark. */
  markMinDistance: 15.0,
  /** Run-with-ball distance before a bounce/touch-down is required. */
  runBounceMetres: 15.0,
  /** Protected area around the mark (2026 stand rule: 5 m). */
  protectedAreaMetres: 5.0,
  /** Seconds allowed to bring the ball back into play (mark/free/kick-in). */
  restartSeconds: 8.0,
};
