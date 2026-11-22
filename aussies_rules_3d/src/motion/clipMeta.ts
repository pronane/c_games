/**
 * Arena Motion Engine: shared clip metadata.
 * Pure TypeScript; safe in the match sim, the renderer and tests.
 */
export const BALL_STATES = ['None', 'Possessed', 'Approaching', 'Contested', 'Aerial'] as const;
export type BallState = (typeof BALL_STATES)[number];

export const CLIP_CATEGORIES = [
  'Locomotion', 'Approach', 'FirstTouch', 'Shield', 'Cut', 'Kick', 'Pass', 'Tackle',
  'KeeperDive', 'Celebrate', 'Idle', 'Recovery', 'Keeper', 'Skill', 'Conduct',
] as const;
export type ClipCategory = (typeof CLIP_CATEGORIES)[number];

export const FOOT_SIDES = ['Left', 'Right'] as const;
export type FootSide = (typeof FOOT_SIDES)[number];

export interface ClipMeta {
  id: string;
  category: ClipCategory;
  duration: number;
  /** Normalized 0..1 contact time, or -1 when the clip has no contact event. */
  contactFraction: number;
  /** Normalized plant phases in clip-cycle coordinates. */
  footPlantFrames: number[];
  footPlantSides: FootSide[];
  rootVelocityX: number;
  rootVelocityZ: number;
  preferredSpeed: number;
  preferredTurnRate: number;
  ballState: BallState;
  tags: string[];
  boneCount: number;
  loop: boolean;
}

export function footPlantSideAt(meta: ClipMeta, index: number): FootSide {
  return meta.footPlantSides.length === meta.footPlantFrames.length
    ? meta.footPlantSides[index]
    : index % 2 === 0
      ? 'Left'
      : 'Right';
}
export function hasContact(meta: ClipMeta): boolean {
  return meta.contactFraction >= 0 && meta.contactFraction <= 1;
}
/** Authored for one engine action (tag "dedicated"): never picked by category. */
export function isDedicated(meta: ClipMeta): boolean {
  return meta.tags.some((t) => t.toLowerCase() === 'dedicated');
}
export function isOneShot(c: ClipCategory): boolean {
  return c === 'FirstTouch' || c === 'Cut' || c === 'Kick' || c === 'Pass' || c === 'Tackle'
    || c === 'KeeperDive' || c === 'Celebrate' || c === 'Recovery';
}
export function isLocomotionCategory(c: ClipCategory): boolean {
  return c === 'Locomotion' || c === 'Idle';
}
export function rootVelocityLength(meta: ClipMeta): number {
  return Math.hypot(meta.rootVelocityX, meta.rootVelocityZ);
}

export class MotionFormatError extends Error {}

/** Strict reader for the AFL clip manifest (public/assets/afl_motion.json). */
export function parseClipManifest(json: unknown): ClipMeta[] {
  if (typeof json !== 'object' || json === null) throw new MotionFormatError('Clip manifest root must be an object.');
  const root = json as Record<string, unknown>;
  if (Number(root.version) !== 1) throw new MotionFormatError('Unsupported clip manifest version; expected 1.');
  if (!Array.isArray(root.clips)) throw new MotionFormatError('Clip manifest must contain a clips array.');

  const result: ClipMeta[] = [];
  for (const item of root.clips as Record<string, unknown>[]) {
    const id = requiredString(item, 'id');
    const category = requiredString(item, 'category') as ClipCategory;
    if (!CLIP_CATEGORIES.includes(category)) throw new MotionFormatError(`Unknown clip category '${category}' for '${id}'.`);
    const ballState = optionalString(item, 'ballState', 'None') as BallState;
    if (!BALL_STATES.includes(ballState)) throw new MotionFormatError(`Unknown ballState '${ballState}' for '${id}'.`);
    const duration = requiredNumber(item, 'duration');
    if (!Number.isFinite(duration) || duration <= 0) throw new MotionFormatError(`Clip '${id}' must have a finite positive duration.`);
    const contact = optionalNumber(item, 'contactFraction', -1);
    if (contact < -1 || contact > 1) throw new MotionFormatError(`Clip '${id}' has contactFraction outside [-1,1].`);
    const feet = readFloatArray(item, 'footPlantFrames');
    for (const phase of feet) {
      if (!Number.isFinite(phase) || phase < 0 || phase > 1) throw new MotionFormatError(`Clip '${id}' has a foot plant outside [0,1].`);
    }
    const footSidesRaw = readStringArray(item, 'footPlantSides');
    const footPlantSides = footSidesRaw as FootSide[];
    for (const side of footPlantSides) {
      if (!FOOT_SIDES.includes(side)) throw new MotionFormatError(`Clip '${id}' has unknown foot plant side '${side}'.`);
    }
    const preferredSpeed = optionalNumber(item, 'preferredSpeed', 0);
    if (preferredSpeed < 0 || !Number.isFinite(preferredSpeed)) throw new MotionFormatError(`Clip '${id}' has invalid preferredSpeed.`);
    const preferredTurnRate = optionalNumber(item, 'preferredTurnRate', 0);
    if (!Number.isFinite(preferredTurnRate)) throw new MotionFormatError(`Clip '${id}' has invalid preferredTurnRate.`);
    const boneCount = optionalInteger(item, 'boneCount', 0);
    if (boneCount <= 0) throw new MotionFormatError(`Clip '${id}' has an invalid boneCount.`);
    const tags = readStringArray(item, 'tags');
    result.push({
      id,
      category,
      duration,
      contactFraction: contact,
      footPlantFrames: feet,
      footPlantSides,
      rootVelocityX: optionalNumber(item, 'rootVelocityX', 0),
      rootVelocityZ: optionalNumber(item, 'rootVelocityZ', 0),
      preferredSpeed,
      preferredTurnRate,
      ballState,
      tags,
      boneCount,
      loop: optionalBoolean(item, 'loop', false),
    });
  }
  return result;
}

function requiredString(item: Record<string, unknown>, field: string): string {
  const v = item[field];
  if (typeof v !== 'string' || v.trim().length === 0) throw new MotionFormatError(`Clip manifest field '${field}' is required and must be a non-empty string.`);
  return v;
}
function optionalString(item: Record<string, unknown>, field: string, fallback: string): string {
  const v = item[field];
  return typeof v === 'string' && v.length > 0 ? v : fallback;
}
function requiredNumber(item: Record<string, unknown>, field: string): number {
  const v = item[field];
  const n = typeof v === 'number' ? v : NaN;
  if (!Number.isFinite(n)) throw new MotionFormatError(`Clip manifest field '${field}' must be a finite number.`);
  return n;
}
function optionalNumber(item: Record<string, unknown>, field: string, fallback: number): number {
  const n = Number(item[field]);
  return Number.isFinite(n) ? n : fallback;
}
function optionalInteger(item: Record<string, unknown>, field: string, fallback: number): number {
  const v = item[field];
  return typeof v === 'number' && Number.isInteger(v) ? v : fallback;
}
function optionalBoolean(item: Record<string, unknown>, field: string, fallback: boolean): boolean {
  const v = item[field];
  return typeof v === 'boolean' ? v : fallback;
}
function readFloatArray(item: Record<string, unknown>, field: string): number[] {
  const v = item[field];
  if (!Array.isArray(v)) return [];
  return v.map((x) => Number(x));
}
function readStringArray(item: Record<string, unknown>, field: string): string[] {
  const v = item[field];
  if (!Array.isArray(v)) return [];
  return v.filter((x): x is string => typeof x === 'string');
}
