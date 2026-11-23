/**
 * Arena Motion Engine: per-player runtime state.
 * Port of arena-fc Scripts/Core/Animation/MotionState.cs with AFL intent names.
 * Runtime animation state is presentation data. It is intentionally separate from
 * the match sim so visuals can never alter authoritative match outcomes.
 */
import type { BallState } from './clipMeta';
import type { PlayerIntent } from './motionEngine';

export class MotionState {
  /** Normalized source phase (0..1). Loops wrap; one-shots clamp. */
  phase = 0;
  blendWeight = 1;
  nextPhase = 0;
  crossfadeRemaining = 0;
  crossfadeDuration = 0.12;
  playbackScale = 1;
  /** Feature row the last motion-matching search chose; -1 = rule selector. */
  motionMatchRowIndex = -1;
  /** Seconds since the last motion-matching search (locomotion re-queries ~10x/s). */
  sinceQuery = 0;
  /** The pose shown on the previous update (survives a one-shot reset), so the next
   * search starts from where the body actually is. */
  lastPoseClipId = '';
  lastPosePhase = 0;
  speed = 0;
  turnRate = 0;
  ball: BallState = 'None';
  lastIntent: PlayerIntent = 'none';
  timeSinceContact = 99;
  contactCrossed = false;
  footPlantedLeft = false;
  footPlantedRight = false;

  constructor(
    public currentClipId = '',
    public nextClipId = '',
  ) {}

  /** The render clip and phase the mixer should present right now. */
  get renderClipId(): string {
    return this.nextClipId.length > 0 ? this.nextClipId : this.currentClipId;
  }
  get renderPhase(): number {
    return this.nextClipId.length > 0 ? this.nextPhase : this.phase;
  }
}

export function initialMotionState(playerIndex: number): MotionState {
  void playerIndex;
  return new MotionState();
}

export function crossed(before: number, after: number, eventPhase: number, loop: boolean): boolean {
  if (loop) {
    if (before <= after) return before < eventPhase && after >= eventPhase;
    return eventPhase > before || eventPhase <= after;
  }
  return before < eventPhase && after >= eventPhase;
}
