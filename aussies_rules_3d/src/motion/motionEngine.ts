/**
 * Arena Motion Engine: deterministic clip selection and phase policy.
 * Exact port of arena-fc Scripts/Core/Animation/MotionEngine.cs, minus the 18-bone
 * gate (the AFL/GAA squad rig has 52 joints) and with AFL intent mapping.
 */
import {
  type BallState,
  type ClipMeta,
  footPlantSideAt,
  isDedicated,
  isLocomotionCategory,
  isOneShot,
  rootVelocityLength,
} from './clipMeta';
import { MotionDatabase, type MotionIntent, type MotionMatch } from './motionDatabase';
import { buildFeatures } from './motionQuery';
import { NO_CONTACT, circularDistance, circularDifference, clamp01, wrap01 } from './motionFeatureLayout';
import { MotionState, crossed as phaseCrossed, initialMotionState } from './motionState';

export const DEFAULT_CROSSFADE_SECONDS = 0.12;
export const LOCOMOTION_QUERY_INTERVAL = 0.1;

/** AFL game actions, mirroring the arena-fc intent vocabulary. */
export type PlayerIntent =
  | 'none' | 'move' | 'sprint' | 'shield'
  | 'pass' | 'through_ball' | 'shoot' | 'trap' | 'cut' | 'tackle' | 'dive'
  | 'celebrate' | 'sprint_stop';

export function selectCategory(intent: PlayerIntent, ball: BallState): string {
  switch (intent) {
    case 'pass':
    case 'through_ball':
      return 'Pass';
    case 'shoot':
      return 'Kick';
    case 'trap':
      return 'FirstTouch';
    case 'shield':
      return 'Shield';
    case 'cut':
      return 'Cut';
    case 'tackle':
      return 'Tackle';
    case 'dive':
      return 'KeeperDive';
    case 'celebrate':
      return 'Celebrate';
    case 'sprint_stop':
      return 'Recovery';
    default:
      if (ball === 'Approaching') return 'Approach';
      return 'Locomotion';
  }
}

/** Deterministic, index-derived phase staggering; no RNG stream. */
export function initialPhase(playerIndex: number): number {
  let x = Math.imul(playerIndex + 1, 0x9e3779b9) >>> 0;
  x = Math.imul(x ^ (x >>> 16), 0x7feb352d) >>> 0;
  x = Math.imul(x ^ (x >>> 15), 0x846ca68b) >>> 0;
  x = Math.imul(x ^ (x >>> 16), 0x7feb352d) >>> 0;
  x ^= x >>> 16;
  return (x & 0x00ffffff) / 0x01000000;
}

export interface MotionVector {
  x: number;
  z: number;
}

export class MotionEngine {
  private clips = new Map<string, ClipMeta>();
  private ordered: ClipMeta[] = [];
  database: MotionDatabase | null = null;

  get clipCount(): number {
    return this.ordered.length;
  }

  loadClips(clips: ClipMeta[]): void {
    this.clips.clear();
    for (const clip of clips) {
      if (!clip.id || clip.duration <= 0) {
        throw new Error('Motion clips require a non-empty id and positive duration.');
      }
      if (this.clips.has(clip.id)) throw new Error(`Duplicate motion clip id '${clip.id}'.`);
      this.clips.set(clip.id, clip);
    }
    this.ordered = [...this.clips.values()].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  }

  tryGetClip(id: string): ClipMeta | null {
    return this.clips.get(id) ?? null;
  }

  update(
    motion: MotionState,
    speed: number,
    turnRate: number,
    ball: BallState,
    intent: PlayerIntent,
    dt: number,
    secondsUntilContact = -1,
    bodyTypeFactor = 1,
    styleTag: string | null = null,
    localVelocity: MotionVector = { x: 0, z: 0 },
    desiredLocalVelocity: MotionVector = { x: 0, z: 0 },
    forcedClipId: string | null = null,
    rateScale = 1,
  ): void {
    dt = Math.max(0, dt);
    motion.contactCrossed = false;
    motion.speed = Math.max(0, speed);
    motion.turnRate = turnRate;
    motion.ball = ball;
    motion.lastIntent = intent;
    motion.timeSinceContact += dt;

    let selected = this.selectClip(intent, ball, speed, turnRate, bodyTypeFactor, styleTag,
      motion.currentClipId.length > 0 ? motion.currentClipId : null);
    const forcedFromId = forcedClipId != null && this.clips.has(forcedClipId) ? forcedClipId : null;
    if (forcedFromId) selected = this.clips.get(forcedFromId)!;

    let matchedPhase: number | null = null;
    motion.sinceQuery += dt;
    if (selected && this.database) {
      const switching = selected.id !== motion.renderClipId;
      const gait = selected.loop && isLocomotionCategory(selected.category);
      if (switching || (gait && motion.sinceQuery >= LOCOMOTION_QUERY_INTERVAL)) {
        motion.sinceQuery = 0;
        const match = this.match(motion, selected, ball, intent, turnRate, styleTag,
          localVelocity, desiredLocalVelocity, secondsUntilContact, forcedFromId);
        if (match && this.clips.has(match.row.clipId)) {
          const mc = this.clips.get(match.row.clipId)!;
          const sameSpot = mc.id === motion.renderClipId
            && circularDistance(motion.renderPhase, match.row.phase) < 0.15;
          if (!sameSpot || switching) {
            selected = mc;
            matchedPhase = match.row.phase;
          }
          motion.motionMatchRowIndex = match.rowIndex;
        }
      }
    }
    if (!selected) {
      if (motion.nextClipId.length > 0) this.commitTransition(motion);
      motion.playbackScale = 1;
      this.updateFootPlants(motion, null, motion.phase);
      return;
    }

    if (motion.currentClipId.length === 0 && motion.nextClipId.length === 0) {
      motion.currentClipId = selected.id;
      motion.phase = matchedPhase ?? (selected.loop ? wrap01(motion.phase) : 0);
      motion.blendWeight = 1;
    } else if (selected.id !== motion.renderClipId || matchedPhase != null) {
      if (motion.nextClipId.length > 0) this.commitTransition(motion);
      const from = this.clips.get(motion.currentClipId) ?? selected;
      const start = matchedPhase ?? computeStartPhase(from, selected, motion.phase, intent);
      motion.nextClipId = selected.id;
      motion.nextPhase = selected.loop ? wrap01(start) : clamp01(start);
      motion.crossfadeDuration = DEFAULT_CROSSFADE_SECONDS;
      motion.crossfadeRemaining = motion.crossfadeDuration;
      motion.blendWeight = 0;
    }

    const current = this.clips.get(motion.currentClipId) ?? selected;
    const scale = playbackScale(selected, speed, intent, secondsUntilContact,
      motion.nextClipId.length > 0 ? motion.nextPhase : motion.phase) * Math.max(0, rateScale);
    motion.playbackScale = scale;
    const oldPhase = motion.nextClipId.length > 0 ? motion.nextPhase : motion.phase;
    if (motion.nextClipId.length > 0) {
      const next = this.clips.get(motion.nextClipId);
      if (next) motion.nextPhase = advancePhase(next, motion.nextPhase, dt, scale);
      const currentScale = playbackScale(current, speed, intent, secondsUntilContact, motion.phase)
        * Math.max(0, rateScale);
      motion.phase = advancePhase(current, motion.phase, dt, currentScale);
      motion.crossfadeRemaining = Math.max(0, motion.crossfadeRemaining - dt);
      motion.blendWeight = motion.crossfadeDuration <= 0
        ? 1
        : clamp01(1 - motion.crossfadeRemaining / motion.crossfadeDuration);
      if (motion.crossfadeRemaining <= 0) this.commitTransition(motion);
    } else {
      motion.phase = advancePhase(current, motion.phase, dt, scale);
    }

    const visible = this.clips.get(motion.renderClipId) ?? selected;
    const visiblePhase = motion.renderPhase;
    if (visible.contactFraction >= 0
      && phaseCrossed(oldPhase, visiblePhase, visible.contactFraction, visible.loop)) {
      motion.contactCrossed = true;
      motion.timeSinceContact = 0;
    }
    this.updateFootPlants(motion, visible, visiblePhase);
    motion.lastPoseClipId = motion.renderClipId;
    motion.lastPosePhase = motion.renderPhase;
  }

  /** Speed-band hysteresis: the currently playing clip is kept until another clip is
   * clearly better (HYSTERESIS_SPEED m/s). Per-call state only — the engine itself
   * holds no player data. */
  static readonly HYSTERESIS_SPEED = 0.35;

  selectClip(
    intent: PlayerIntent,
    ball: BallState,
    speed: number,
    turnRate: number,
    bodyTypeFactor = 1,
    styleTag: string | null = null,
    keepClipId: string | null = null,
  ): ClipMeta | null {
    const category = selectCategory(intent, ball);
    // Standing still is idle, not the slowest "locomotion" clip.
    if (category === 'Locomotion' && ball !== 'Possessed' && speed < 0.35) {
      const idle = this.selectBest('Idle', 'None', 0, 0, 1, styleTag, keepClipId);
      if (idle) return idle;
    }
    const best = this.selectBest(category as ClipMeta['category'], ball, speed, turnRate, bodyTypeFactor, styleTag, keepClipId);
    if (best) return best;
    if (category !== 'Locomotion') {
      const loco = this.selectBest('Locomotion', ball, speed, turnRate, bodyTypeFactor, styleTag, keepClipId);
      if (loco) return loco;
    }
    return this.selectBest('Idle', 'None', 0, 0, 1, null);
  }

  private match(
    motion: MotionState,
    selected: ClipMeta,
    ball: BallState,
    intent: PlayerIntent,
    turnRate: number,
    styleTag: string | null,
    localVelocity: MotionVector,
    desiredLocalVelocity: MotionVector,
    secondsUntilContact: number,
    forcedClipId: string | null,
  ): MotionMatch | null {
    if (!this.database) return null;
    const poseClip = motion.renderClipId.length > 0 ? motion.renderClipId : motion.lastPoseClipId;
    const posePhase = motion.renderClipId.length > 0 ? motion.renderPhase : motion.lastPosePhase;
    const pose = (poseClip.length > 0 ? this.database.tryGetPoseFeatures(poseClip, posePhase) : null) ?? new Float32Array(8);
    const ttc = secondsUntilContact > 0 ? secondsUntilContact : NO_CONTACT;
    const features = buildFeatures(pose, localVelocity.x, localVelocity.z, turnRate,
      desiredLocalVelocity.x, desiredLocalVelocity.z, turnRate, ttc);
    let forced = forcedClipId != null && this.clips.has(forcedClipId) ? forcedClipId : null;
    if (selected.tags.some((t) => t.toLowerCase() === 'dedicated')) forced = selected.id;
    return this.database.trySearch({
      features,
      category: selected.category,
      ball,
      intent: toMotionIntent(intent),
      styleTag: styleTag ?? '',
      currentClipId: selected.loop ? motion.renderClipId : '',
      currentPhase: motion.renderPhase,
      forcedClipId: forced ?? '',
    });
  }

  private selectBest(
    category: ClipMeta['category'],
    ball: BallState,
    speed: number,
    turnRate: number,
    bodyTypeFactor: number,
    styleTag: string | null,
    keepClipId: string | null = null,
  ): ClipMeta | null {
    let best: ClipMeta | null = null;
    let bestScore = Number.POSITIVE_INFINITY;
    let exactBallStateExists = false;
    let neutralBallStateExists = false;
    for (const c of this.ordered) {
      if (c.category !== category) continue;
      if (c.ballState === ball) exactBallStateExists = true;
      if (c.ballState === 'None') neutralBallStateExists = true;
    }
    for (const c of this.ordered) {
      if (isDedicated(c)) continue; // only ever played for the action that names it
      if (c.category !== category) continue;
      if (exactBallStateExists ? c.ballState !== ball
        : neutralBallStateExists && c.ballState !== 'None') continue;
      const speedError = Math.abs(c.preferredSpeed - speed) * clamp(bodyTypeFactor, 0.5, 1.5);
      const turnError = Math.abs(c.preferredTurnRate - turnRate) * 0.35;
      const rootError = Math.abs(rootVelocityLength(c) - speed) * 0.15;
      const tagBonus = styleTag != null
        && c.tags.some((t) => t.toLowerCase() === styleTag.toLowerCase()) ? -0.1 : 0;
      const hysteresis = keepClipId != null && c.id === keepClipId ? MotionEngine.HYSTERESIS_SPEED : 0;
      const score = speedError + turnError + rootError + tagBonus - hysteresis;
      if (score < bestScore) {
        bestScore = score;
        best = c;
      }
    }
    return best;
  }

  private commitTransition(motion: MotionState): void {
    if (motion.nextClipId.length === 0) return;
    motion.currentClipId = motion.nextClipId;
    motion.phase = motion.nextPhase;
    motion.nextClipId = '';
    motion.nextPhase = motion.phase;
    motion.crossfadeRemaining = 0;
    motion.blendWeight = 1;
  }

  private updateFootPlants(motion: MotionState, clip: ClipMeta | null, phase: number): void {
    motion.footPlantedLeft = false;
    motion.footPlantedRight = false;
    if (!clip || clip.footPlantFrames.length === 0) return;
    for (let i = 0; i < clip.footPlantFrames.length; i++) {
      if (circularDistance(phase, clip.footPlantFrames[i]) > 0.035) continue;
      if (footPlantSideAt(clip, i) === 'Left') motion.footPlantedLeft = true;
      else motion.footPlantedRight = true;
    }
  }
}

export function computeStartPhase(from: ClipMeta, to: ClipMeta, currentPhase: number, intent: PlayerIntent): number {
  if (!to.loop || isOneShot(to.category)
    || intent === 'pass' || intent === 'through_ball' || intent === 'shoot' || intent === 'trap'
    || intent === 'tackle' || intent === 'dive' || intent === 'celebrate') {
    return 0;
  }
  if (from.loop && isLocomotionCategory(from.category) && isLocomotionCategory(to.category)) {
    return alignToNearestFootEvent(from, to, currentPhase);
  }
  return clamp01(currentPhase);
}

/** Map the nearest source plant to the nearest target plant for that same side,
 * preserving the circular offset from the source event. */
export function alignToNearestFootEvent(from: ClipMeta, to: ClipMeta, phase: number): number {
  if (from.footPlantFrames.length === 0 || to.footPlantFrames.length === 0) return wrap01(phase);
  let nearest = 0;
  let bestDistance = Number.POSITIVE_INFINITY;
  for (let i = 0; i < from.footPlantFrames.length; i++) {
    const d = circularDistance(phase, from.footPlantFrames[i]);
    if (d < bestDistance) {
      bestDistance = d;
      nearest = i;
    }
  }
  const sourcePlant = from.footPlantFrames[nearest];
  const side = footPlantSideAt(from, nearest);
  let targetIndex = -1;
  bestDistance = Number.POSITIVE_INFINITY;
  for (let i = 0; i < to.footPlantFrames.length; i++) {
    if (footPlantSideAt(to, i) !== side) continue;
    const d = circularDistance(sourcePlant, to.footPlantFrames[i]);
    if (d < bestDistance) {
      bestDistance = d;
      targetIndex = i;
    }
  }
  if (targetIndex < 0) return wrap01(phase);
  return wrap01(to.footPlantFrames[targetIndex] + circularDifference(phase, sourcePlant));
}

export function advancePhase(clip: ClipMeta, phase: number, dt: number, playbackScale: number): number {
  if (clip.duration <= 1e-6 || dt <= 0) return clip.loop ? wrap01(phase) : clamp01(phase);
  const advanced = phase + (dt * Math.max(0, playbackScale)) / clip.duration;
  return clip.loop ? wrap01(advanced) : clamp01(advanced);
}

export function contactAlignedPlaybackScale(clip: ClipMeta, secondsUntilContact: number): number {
  if (clip.contactFraction <= 0 || secondsUntilContact <= 0.001) return 1;
  return (clip.duration * clip.contactFraction) / secondsUntilContact;
}

function playbackScale(
  clip: ClipMeta,
  speed: number,
  _intent: PlayerIntent,
  secondsUntilContact: number,
  phase = 0,
): number {
  if (clip.contactFraction >= 0 && secondsUntilContact > 0.001) {
    // Play the wind-up that is LEFT (from the entry frame) in the time left.
    const remaining = (clip.contactFraction - clamp01(phase)) * clip.duration;
    if (remaining > 0.01) return clamp(remaining / secondsUntilContact, 0.4, 3);
    return 1;
  }
  if (isLocomotionCategory(clip.category) && clip.preferredSpeed > 0.1) {
    return clamp(speed / clip.preferredSpeed, 0.45, 2.8);
  }
  return 1;
}

function toMotionIntent(intent: PlayerIntent): MotionIntent {
  switch (intent) {
    case 'none': return 'none';
    case 'move': return 'move';
    case 'sprint': return 'sprint';
    case 'shield': return 'shield';
    default: return 'action';
  }
}

function clamp(v: number, lo: number, hi: number): number {
  return v < lo ? lo : v > hi ? hi : v;
}

export { initialMotionState };
