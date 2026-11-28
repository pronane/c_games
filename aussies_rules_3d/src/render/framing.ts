/**
 * Camera framing — pure math helpers that keep subjects (the ball, the
 * controlled player) inside the frame. No rendering, no state: everything
 * here is deterministic and unit-tested.
 *
 * The broadcast views each have their own position formula, which can lose
 * the ball on long kicks or split the ball and the controlled player across
 * opposite frame edges. `enforceFraming` is a view-agnostic post-step: if
 * every subject already sits inside a safe NDC box it changes nothing;
 * otherwise it re-frames (pulls back along the current view ray and re-aims
 * at the weighted centroid) until both fit with margin.
 *
 * The re-frame keeps the view-ray direction and only scales out the distance,
 * so the spread of the subjects in the final camera frame is exactly the one
 * solved for — the guarantee holds exactly, not approximately.
 *
 * Conventions match three.js: world space is y-up, camera looks down -z,
 * NDC usable box is [-margin, +margin].
 */
import * as THREE from 'three';

export const SAFE_MARGIN = 0.78; // NDC half-extent that counts as "in frame, comfortably"
export const MIN_FIT_DISTANCE = 6; // never fit tighter than this (metres)
const FIT_PAD = 0.98; // solve to 98% of the margin so float error can't push a subject out

export interface FitSubject {
  x: number;
  y: number;
  z: number;
  /** Relative weight in the centroid. The ball is the star: default 1.25. */
  weight?: number;
}

export interface FrameFix {
  position: THREE.Vector3;
  lookAt: THREE.Vector3;
}

const UP = new THREE.Vector3(0, 1, 0);

/** Right/up camera-plane basis for a view ray (dir = direction camera looks). */
function basisFor(dir: THREE.Vector3) {
  let right = new THREE.Vector3().crossVectors(dir, UP);
  if (right.lengthSq() < 1e-8) {
    // Near-vertical view (tactical): pick a stable horizontal basis.
    right = new THREE.Vector3(1, 0, 0);
  } else {
    right.normalize();
  }
  const upCam = new THREE.Vector3().crossVectors(right, dir).normalize();
  return { right, upCam };
}

/** NDC coords of a world point for a camera with the given fov/aspect. */
export function projectNdc(
  position: THREE.Vector3,
  lookAt: THREE.Vector3,
  fovYDeg: number,
  aspect: number,
  point: THREE.Vector3 | { x: number; y: number; z: number },
): { x: number; y: number } | null {
  const cam = new THREE.PerspectiveCamera(fovYDeg, aspect, 0.1, 1000);
  cam.position.copy(position);
  cam.lookAt(lookAt);
  cam.updateMatrixWorld(true);
  cam.updateProjectionMatrix();
  const v = point instanceof THREE.Vector3
    ? point.clone()
    : new THREE.Vector3(point.x, point.y, point.z);
  if (v.clone().applyMatrix4(cam.matrixWorldInverse).z >= -cam.near) return null;
  v.project(cam);
  if (!Number.isFinite(v.x) || !Number.isFinite(v.y)) return null;
  return { x: v.x, y: v.y };
}

/** True when every subject sits inside the safe NDC box. */
export function subjectsInFrame(
  position: THREE.Vector3,
  lookAt: THREE.Vector3,
  fovYDeg: number,
  aspect: number,
  subjects: FitSubject[],
  margin = SAFE_MARGIN,
): boolean {
  for (const s of subjects) {
    const ndc = projectNdc(position, lookAt, fovYDeg, aspect, s);
    if (!ndc) return false;
    if (Math.abs(ndc.x) > margin || Math.abs(ndc.y) > margin) return false;
  }
  return true;
}

/**
 * Re-frame `position`/`lookAt` so every subject is inside the safe box.
 * Returns null when the current framing is already acceptable (normal play,
 * zero behaviour change). The view ray (position − centroid) is kept; only
 * the distance is scaled out as far as required, and lookAt re-aims at the
 * weighted centroid (ball-biased).
 */
export function enforceFraming(
  position: THREE.Vector3,
  lookAt: THREE.Vector3,
  fovYDeg: number,
  aspect: number,
  subjects: FitSubject[],
  margin = SAFE_MARGIN,
): FrameFix | null {
  if (subjects.length === 0) return null;
  // Nothing to do when everything is already comfortably in frame.
  if (subjectsInFrame(position, lookAt, fovYDeg, aspect, subjects, margin)) return null;

  // Weighted centroid (ball-biased).
  let wsum = 0;
  const centroid = new THREE.Vector3();
  for (const s of subjects) {
    const w = s.weight ?? 1;
    wsum += w;
    centroid.addScaledVector(new THREE.Vector3(s.x, s.y, s.z), w);
  }
  centroid.divideScalar(wsum);

  // View ray stays fixed by construction; solve for the distance in THIS frame.
  const viewDir = position.clone().sub(centroid);
  const currentDist = viewDir.length();
  if (currentDist < 1e-6) viewDir.set(0, 0, 1); // degenerate: any horizontal ray
  viewDir.normalize();
  const dir = viewDir.clone().negate(); // camera looks along −viewDir
  const { right, upCam } = basisFor(dir);

  const tanHalfV = Math.tan(THREE.MathUtils.degToRad(fovYDeg) / 2);
  const tanHalfH = tanHalfV * aspect;
  const fitMargin = margin * FIT_PAD;
  let need = MIN_FIT_DISTANCE;
  const tmp = new THREE.Vector3();
  for (const s of subjects) {
    tmp.set(s.x - centroid.x, s.y - centroid.y, s.z - centroid.z);
    // Perspective depth differs per subject: depth = distance - towardCamera.
    const towardCamera = tmp.dot(viewDir);
    need = Math.max(need,
      towardCamera + 0.6,
      towardCamera + Math.abs(tmp.dot(right)) / (tanHalfH * fitMargin),
      towardCamera + Math.abs(tmp.dot(upCam)) / (tanHalfV * fitMargin));
  }
  const finalDist = Math.max(currentDist, need);
  const newPos = centroid.clone().addScaledVector(viewDir, finalDist);
  return { position: newPos, lookAt: centroid };
}
