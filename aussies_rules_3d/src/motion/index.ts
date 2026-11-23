/** Arena Motion Engine — public surface for aussies_rules_3d. */
export * from './motionFeatureLayout';
export * from './clipMeta';
export * from './motionQuery';
export {
  MotionDatabase,
  type MotionFeatureRow,
  type MotionMatch,
  type MotionQuery as DatabaseQuery,
  type MotionIntent,
} from './motionDatabase';
export {
  MotionEngine,
  DEFAULT_CROSSFADE_SECONDS,
  LOCOMOTION_QUERY_INTERVAL,
  initialPhase,
  selectCategory,
  computeStartPhase,
  alignToNearestFootEvent,
  advancePhase,
  contactAlignedPlaybackScale,
  type PlayerIntent,
  type MotionVector,
} from './motionEngine';
export { initialMotionState, crossed, MotionState } from './motionState';
