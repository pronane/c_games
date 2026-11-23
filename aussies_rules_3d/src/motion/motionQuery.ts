/**
 * Arena Motion Engine: raw-unit query builder.
 * Exact port of arena-fc Scripts/Core/Animation/MotionQuery.cs.
 * Velocity/facing inputs are already in the current facing-root XZ basis.
 */
import {
  DIMENSIONS,
  NO_CONTACT,
  SCHEMA_VERSION,
  TIME_TO_CONTACT,
  TRAJECTORY_TIMES,
} from './motionFeatureLayout';
import { MotionFormatError } from './clipMeta';

export function buildFeatures(
  currentPoseFeatures: Float32Array,
  rootVelX: number,
  rootVelZ: number,
  yawRate: number,
  desiredVelX: number,
  desiredVelZ: number,
  desiredYawRate: number,
  timeToContact: number = NO_CONTACT,
): Float32Array {
  if (currentPoseFeatures.length !== 8) {
    throw new MotionFormatError('Current pose must contain the 8 foot position/velocity features.');
  }
  for (const v of [rootVelX, rootVelZ, yawRate, desiredVelX, desiredVelZ, desiredYawRate]) {
    if (!Number.isFinite(v)) throw new MotionFormatError('Motion query inputs must be finite.');
  }
  const features = new Float32Array(DIMENSIONS);
  features.set(currentPoseFeatures.subarray(0, 8), 0);
  features[8] = rootVelX;
  features[9] = rootVelZ;
  features[10] = yawRate;
  for (let i = 0; i < TRAJECTORY_TIMES.length; i++) {
    const t = TRAJECTORY_TIMES[i];
    const decay = Math.exp(-4 * t);
    const integratedGain = (1 - decay) * 0.25;
    features[11 + i * 2] = desiredVelX * t + (rootVelX - desiredVelX) * integratedGain;
    features[12 + i * 2] = desiredVelZ * t + (rootVelZ - desiredVelZ) * integratedGain;
    const yaw = desiredYawRate * t;
    features[17 + i * 2] = Math.sin(yaw);
    features[18 + i * 2] = Math.cos(yaw);
  }
  features[TIME_TO_CONTACT] =
    Number.isFinite(timeToContact) && timeToContact >= 0 ? Math.min(timeToContact, NO_CONTACT) : NO_CONTACT;
  return features;
}

export { SCHEMA_VERSION };
