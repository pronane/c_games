/**
 * Arena Motion Engine: the baked feature table and the brute-force search.
 * Exact port of arena-fc Scripts/Core/Animation/MotionDatabase.cs, schema v2.
 * One C# detail is intentionally not ported: `Intent` as a hard locomotion gate
 * (AFL's intent enum lives in the sim; the query carries `locomotionIntent`).
 */
import {
  BALL_STATES,
  CLIP_CATEGORIES,
  type BallState,
  type ClipCategory,
} from './clipMeta';
import {
  DIMENSIONS,
  SCHEMA_VERSION,
  TIME_TO_CONTACT,
  TRAJECTORY_TIMES,
  matchesLayout,
  circularDistance,
} from './motionFeatureLayout';
import { MotionFormatError } from './clipMeta';

export type MotionIntent = 'none' | 'move' | 'sprint' | 'shield' | 'action';

export interface MotionFeatureRow {
  clipId: string;
  frameIndex: number;
  phase: number;
  category: ClipCategory;
  ballState: BallState;
  styleTag: string;
  features: Float32Array;
}

export interface MotionMatch {
  row: MotionFeatureRow;
  rowIndex: number;
  cost: number;
}

export interface MotionQuery {
  features: Float32Array;
  category: ClipCategory;
  ball: BallState;
  intent: MotionIntent;
  styleTag?: string;
  currentClipId?: string;
  currentPhase?: number;
  switchPenalty?: number;
  temporalPenalty?: number;
  forcedClipId?: string;
}

const CURRENT_VERSION = 2;

export class MotionDatabase {
  readonly rows: readonly MotionFeatureRow[];
  private readonly mean: Float32Array;
  private readonly stdDev: Float32Array;
  private readonly weights: Float32Array;

  private constructor(rows: MotionFeatureRow[], mean: Float32Array, stdDev: Float32Array, weights: Float32Array) {
    this.rows = rows;
    this.mean = mean;
    this.stdDev = stdDev;
    this.weights = weights;
  }

  get count(): number {
    return this.rows.length;
  }
  get dimensions(): number {
    return DIMENSIONS;
  }

  static parse(json: unknown): MotionDatabase {
    if (typeof json !== 'object' || json === null) throw new MotionFormatError('Motion feature database root must be an object.');
    const root = json as Record<string, unknown>;
    if (intAt(root, 'version') !== CURRENT_VERSION) throw new MotionFormatError(`Unsupported motion database version; expected ${CURRENT_VERSION}.`);
    if (intAt(root, 'featureSchemaVersion') !== SCHEMA_VERSION) throw new MotionFormatError('Motion feature schema version does not match the engine.');
    if (intAt(root, 'dimensions') !== DIMENSIONS) throw new MotionFormatError(`Motion database must have ${DIMENSIONS} dimensions.`);
    if (String(root.space ?? '') !== 'facing_root_xz') throw new MotionFormatError('Motion database coordinate space differs from the engine.');

    if (!matchesLayout(readStrings(root, 'layout'))) throw new MotionFormatError('Motion database feature layout/order differs from the engine.');

    const norm = root.normalization as Record<string, unknown> | undefined;
    if (!norm || String(norm.method ?? '') !== 'zscore') throw new MotionFormatError('Motion database normalization must use the versioned zscore format.');

    const trajectoryTimes = readFloats(root, 'trajectoryTimes', TRAJECTORY_TIMES.length);
    for (let i = 0; i < trajectoryTimes.length; i++) {
      if (Math.abs(trajectoryTimes[i] - TRAJECTORY_TIMES[i]) > 1e-5) throw new MotionFormatError('Motion database trajectory sample times differ from the engine.');
    }
    const mean = readFloats(norm, 'mean', DIMENSIONS);
    const stdDev = readFloats(norm, 'stdDev', DIMENSIONS);
    const weights = readFloats(root, 'weights', DIMENSIONS);
    for (let i = 0; i < DIMENSIONS; i++) {
      if (stdDev[i] <= 0) throw new MotionFormatError(`Motion database stdDev[${i}] must be positive.`);
      if (weights[i] < 0) throw new MotionFormatError(`Motion database weights[${i}] cannot be negative.`);
    }
    if (!Array.isArray(root.rows)) throw new MotionFormatError('Motion database rows must be an array.');

    const seen = new Set<string>();
    const rows: MotionFeatureRow[] = [];
    for (const item of root.rows as Record<string, unknown>[]) {
      const clipId = readString(item, 'clipId');
      const frame = intAt(item, 'frameIndex');
      const phase = floatAt(item, 'phase');
      if (frame < 0 || phase < 0 || phase >= 1) throw new MotionFormatError(`Motion row '${clipId}' has invalid frameIndex or normalized phase.`);
      const category = readString(item, 'category') as ClipCategory;
      if (!CLIP_CATEGORIES.includes(category)) throw new MotionFormatError(`Motion row '${clipId}' has an unknown category.`);
      const ballState = readString(item, 'ballState') as BallState;
      if (!BALL_STATES.includes(ballState)) throw new MotionFormatError(`Motion row '${clipId}' has an unknown ballState.`);
      const styleTag = optionalString(item, 'styleTag', '');
      const features = readFloats(item, 'features', DIMENSIONS);
      for (let i = 0; i < features.length; i++) {
        if (!Number.isFinite(features[i])) throw new MotionFormatError(`Motion row '${clipId}' feature ${i} is not finite.`);
      }
      const key = `${clipId}${frame}`;
      if (seen.has(key)) throw new MotionFormatError(`Duplicate motion payload '${clipId}' frame ${frame}.`);
      seen.add(key);
      rows.push({ clipId, frameIndex: frame, phase, category, ballState, styleTag, features });
    }
    if (rows.length === 0) throw new MotionFormatError('Motion database must contain at least one row.');
    rows.sort((a, b) => (a.clipId < b.clipId ? -1 : a.clipId > b.clipId ? 1 : a.frameIndex - b.frameIndex));
    return new MotionDatabase(rows, mean, stdDev, weights);
  }

  /** The 8 foot position/velocity features of the row nearest a clip phase. */
  tryGetPoseFeatures(clipId: string, phase: number): Float32Array | null {
    let best = -1;
    let bestD = Number.POSITIVE_INFINITY;
    for (let i = 0; i < this.rows.length; i++) {
      const r = this.rows[i];
      if (r.clipId !== clipId) continue;
      const d = Math.abs(r.phase - phase);
      if (d < bestD) {
        bestD = d;
        best = i;
      }
    }
    if (best < 0) return null;
    return this.rows[best].features.subarray(0, 8).slice();
  }

  trySearch(query: MotionQuery): MotionMatch | null {
    const forced = (query.forcedClipId ?? '').length > 0;
    const locomotion = query.category === 'Locomotion';
    if (!forced && locomotion && !isLocomotionIntent(query.intent)) return null;
    if (!forced && !locomotion) return this.trySearchAction(query);
    if (forced) return this.trySearchForced(query);

    let exactBall = false;
    let neutralBall = false;
    for (const row of this.rows) {
      if (row.category !== query.category) continue;
      if (row.ballState === query.ball) exactBall = true;
      if (row.ballState === 'None') neutralBall = true;
    }
    let exactStyle = false;
    const styleTag = query.styleTag ?? '';
    if (styleTag.length > 0) {
      for (const row of this.rows) {
        if (this.eligibleBall(row, query.category, query.ball, exactBall, neutralBall)
          && row.styleTag.toLowerCase() === styleTag.toLowerCase()) {
          exactStyle = true;
          break;
        }
      }
    }

    let bestCost = Number.POSITIVE_INFINITY;
    let bestIndex = -1;
    const switchPenalty = query.switchPenalty ?? 0.08;
    const temporalPenalty = query.temporalPenalty ?? 0.12;
    const currentClipId = query.currentClipId ?? '';
    const currentPhase = query.currentPhase ?? 0;
    for (let i = 0; i < this.rows.length; i++) {
      const row = this.rows[i];
      if (!this.eligibleBall(row, query.category, query.ball, exactBall, neutralBall)) continue;
      if (exactStyle && row.styleTag.toLowerCase() !== styleTag.toLowerCase()) continue;

      let cost = 0;
      for (let d = 0; d < DIMENSIONS; d++) {
        const queryNormalized = (query.features[d] - this.mean[d]) / this.stdDev[d];
        const rowNormalized = (row.features[d] - this.mean[d]) / this.stdDev[d];
        const normalizedDelta = queryNormalized - rowNormalized;
        cost += normalizedDelta * normalizedDelta * this.weights[d];
      }
      if (currentClipId.length > 0) {
        if (currentClipId !== row.clipId) cost += switchPenalty;
        else cost += temporalPenalty * circularDistance(currentPhase, row.phase);
      }
      if (cost < bestCost) {
        bestCost = cost;
        bestIndex = i;
      }
    }
    if (bestIndex < 0) return null;
    return { row: this.rows[bestIndex], rowIndex: bestIndex, cost: bestCost };
  }

  /** One-shot entry search: rows of the query's category (dedicated clips excluded),
   * cost = pose + trajectory + contact timing. */
  private trySearchAction(query: MotionQuery): MotionMatch | null {
    let exactBall = false;
    for (const row of this.rows) {
      if (row.category === query.category && row.styleTag !== 'dedicated' && row.ballState === query.ball) {
        exactBall = true;
        break;
      }
    }
    let bestCost = Number.POSITIVE_INFINITY;
    let bestIndex = -1;
    for (let i = 0; i < this.rows.length; i++) {
      const row = this.rows[i];
      if (row.category !== query.category || row.styleTag === 'dedicated') continue;
      if (exactBall && row.ballState !== query.ball) continue;
      const cost = this.cost(query.features, row, ACTION_ENTRY_SCALE);
      if (cost < bestCost) {
        bestCost = cost;
        bestIndex = i;
      }
    }
    if (bestIndex < 0) return null;
    return { row: this.rows[bestIndex], rowIndex: bestIndex, cost: bestCost };
  }

  private trySearchForced(query: MotionQuery): MotionMatch | null {
    let bestCost = Number.POSITIVE_INFINITY;
    let bestIndex = -1;
    for (let i = 0; i < this.rows.length; i++) {
      const row = this.rows[i];
      if (row.clipId !== query.forcedClipId) continue;
      const cost = this.cost(query.features, row, ACTION_ENTRY_SCALE);
      if (cost < bestCost) {
        bestCost = cost;
        bestIndex = i;
      }
    }
    if (bestIndex < 0) return null;
    return { row: this.rows[bestIndex], rowIndex: bestIndex, cost: bestCost };
  }

  private cost(q: Float32Array, row: MotionFeatureRow, scale: Float32Array | null = null): number {
    let cost = 0;
    for (let d = 0; d < DIMENSIONS; d++) {
      const delta = (q[d] - row.features[d]) / this.stdDev[d];
      cost += delta * delta * this.weights[d] * (scale ? scale[d] : 1);
    }
    return cost;
  }

  private eligibleBall(row: MotionFeatureRow, category: ClipCategory, ball: BallState,
    exactBall: boolean, neutralBall: boolean): boolean {
    if (row.category !== category) return false;
    if (exactBall) return row.ballState === ball;
    if (neutralBall) return row.ballState === 'None';
    return true;
  }
}

/** Entering an action (kick, mark, tackle ...): the action itself sets where the body
 * goes next, so the gait's velocities and planned path count for little; what matters is
 * the wind-up time left and which foot is where. */
const ACTION_ENTRY_SCALE: Float32Array = (() => {
  const s = new Float32Array(DIMENSIONS);
  for (let d = 0; d < DIMENSIONS; d++) s[d] = d < 4 ? 1 : d < 8 ? 0.3 : 0.15;
  s[TIME_TO_CONTACT] = 5;
  return s;
})();

function isLocomotionIntent(intent: MotionIntent): boolean {
  return intent === 'none' || intent === 'move' || intent === 'sprint' || intent === 'shield';
}

/* ---------- strict JSON readers (mirrors ClipManifestLoader conventions) ---------- */

function intAt(e: Record<string, unknown>, name: string): number {
  const v = e[name];
  if (typeof v === 'number' && Number.isInteger(v)) return v;
  throw new MotionFormatError(`Motion database field '${name}' must be an integer.`);
}
function floatAt(e: Record<string, unknown>, name: string): number {
  const v = Number(e[name]);
  if (Number.isFinite(v)) return v;
  throw new MotionFormatError(`Motion database field '${name}' must be numeric.`);
}
function readString(e: Record<string, unknown>, name: string): string {
  const v = e[name];
  if (typeof v === 'string' && v.trim().length > 0) return v;
  throw new MotionFormatError(`Motion database field '${name}' must be a non-empty string.`);
}
function optionalString(e: Record<string, unknown>, name: string, fallback: string): string {
  const v = e[name];
  return typeof v === 'string' ? v : fallback;
}
function readStrings(e: Record<string, unknown>, name: string): string[] {
  const v = e[name];
  if (!Array.isArray(v) || !v.every((x) => typeof x === 'string')) {
    throw new MotionFormatError(`Motion database field '${name}' must be an array of strings.`);
  }
  return v as string[];
}
function readFloats(e: Record<string, unknown>, name: string, expected: number): Float32Array {
  const v = e[name];
  if (!Array.isArray(v) || v.length !== expected) {
    throw new MotionFormatError(`Motion database field '${name}' must be an array of ${expected} numbers.`);
  }
  const out = new Float32Array(expected);
  for (let i = 0; i < expected; i++) {
    const n = Number(v[i]);
    if (!Number.isFinite(n)) throw new MotionFormatError(`Motion database field '${name}[${i}]' is not finite.`);
    out[i] = n;
  }
  return out;
}
