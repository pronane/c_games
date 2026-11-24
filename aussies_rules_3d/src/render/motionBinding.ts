/**
 * MotionBinding — drives a skinned player with the Arena Motion Engine.
 *
 * The engine owns clip selection and phase; three.js only renders the pose.
 * Every GLB clip gets one AnimationAction, `paused` so the mixer applies the
 * engine-computed pose instead of advancing its own clock. During a crossfade
 * the outgoing and incoming clips are weighted (1-blend, blend).
 */
import * as THREE from 'three';
import type { GLTF } from 'three/addons/loaders/GLTFLoader.js';
import {
  MotionDatabase,
  MotionEngine,
  initialMotionState,
  initialPhase,
  parseClipManifest,
  type BallState,
  type ClipMeta,
  type PlayerIntent,
} from '../motion';
import {
  createPlantSide,
  updatePlantSide,
  solveTwoBoneIK,
  MAX_REACH_FACTOR,
  type PlantSide,
} from '../motion/legIk';

export interface MotionAssets {
  engine: MotionEngine;
  meta: Map<string, ClipMeta>;
}

let cached: Promise<MotionAssets | null> | null = null;

/** Fetch and parse the baked AFL motion assets once. Returns null on any
 * failure so callers can fall back to the legacy animation path. */
export function loadMotionAssets(): Promise<MotionAssets | null> {
  if (!cached) {
    cached = (async () => {
      try {
        const [manifestJson, featuresJson] = await Promise.all([
          fetch('./assets/afl_motion.json').then((r) =>
            r.ok ? r.json() : Promise.reject(new Error(`afl_motion.json HTTP ${r.status}`))),
          fetch('./assets/afl_motion_features.json').then((r) =>
            r.ok ? r.json() : Promise.reject(new Error(`afl_motion_features.json HTTP ${r.status}`))),
        ]);
        const clips = parseClipManifest(manifestJson);
        const database = MotionDatabase.parse(featuresJson);
        const engine = new MotionEngine();
        engine.loadClips(clips);
        engine.database = database;
        return { engine, meta: new Map(clips.map((c) => [c.id, c])) };
      } catch (err) {
        console.warn('[motion] baked motion assets unavailable, using legacy clips:', err);
        return null;
      }
    })();
  }
  return cached;
}

/** Deterministic per-player gait rate (0.94..1.06) — seed variety until
 * dedicated light/heavy gait clips are authored. */
export function gaitStyle(playerId: number): number {
  const x = Math.sin(playerId * 127.1 + 311.7) * 43758.5453;
  return 0.94 + (x - Math.floor(x)) * 0.12;
}

/**
 * Planted-foot IK is an opt-in experiment (?plantik=1) ported from the Gaelic
 * branch. Off by default until it has had a GPU/visual pass — see
 * docs/MOTION_IK.md. Pure parser so it is unit-testable outside the browser.
 */
export function parsePlantIkFlag(search: string): boolean {
  try {
    return new URLSearchParams(search).get('plantik') === '1';
  } catch {
    return false;
  }
}
export const PLANT_IK_ENABLED =
  typeof window !== 'undefined' ? parsePlantIkFlag(window.location.search) : false;

function wrapAngle(a: number): number {
  while (a > Math.PI) a -= 2 * Math.PI;
  while (a < -Math.PI) a += 2 * Math.PI;
  return a;
}

/** Rotate `bone` in world space so its local +segment axis (fromDir) maps to
 * toDir — three.js equivalent of Gaelic `aimBone` (quatFromTo premultiplied). */
export function aimBoneWorld(
  bone: THREE.Object3D,
  fromDir: THREE.Vector3,
  toDir: THREE.Vector3,
): void {
  const from = fromDir.clone();
  const to = toDir.clone();
  if (from.lengthSq() < 1e-10 || to.lengthSq() < 1e-10) return;
  from.normalize();
  to.normalize();
  const delta = new THREE.Quaternion().setFromUnitVectors(from, to);
  const parentQuat = bone.parent
    ? bone.parent.getWorldQuaternion(new THREE.Quaternion())
    : new THREE.Quaternion();
  const worldQuat = bone.getWorldQuaternion(new THREE.Quaternion());
  const newWorld = delta.multiply(worldQuat);
  bone.quaternion.copy(parentQuat.invert().multiply(newWorld));
}

/**
 * Re-aim a thigh→calf→foot chain so the foot lands on `target` (world space),
 * preserving bone segment lengths. `root` is the common ancestor — its world
 * matrices are refreshed between the four write steps. Exported for tests.
 * Returns false when the solve degenerated (bones left untouched).
 */
export function solveLegChainWorld(
  thigh: THREE.Object3D,
  calf: THREE.Object3D,
  foot: THREE.Object3D,
  target: THREE.Vector3,
  forward: THREE.Vector3,
  root: THREE.Object3D,
): boolean {
  root.updateMatrixWorld(true);
  const hipW = thigh.getWorldPosition(new THREE.Vector3());
  const kneeW = calf.getWorldPosition(new THREE.Vector3());
  const footW = foot.getWorldPosition(new THREE.Vector3());
  const l1 = hipW.distanceTo(kneeW);
  const l2 = kneeW.distanceTo(footW);
  if (l1 < 0.05 || l2 < 0.05) return false;
  const solveKnee = kneeW.clone();
  const solveFoot = footW.clone();
  solveTwoBoneIK(hipW, solveKnee, solveFoot, target.clone(), forward);
  const clampedTarget = solveFoot.clone();
  // 1) rotate the thigh so hip→knee points along hip→solvedKnee
  aimBoneWorld(thigh, kneeW.clone().sub(hipW), solveKnee.clone().sub(hipW));
  root.updateMatrixWorld(true);
  // 2) place the calf joint at the solved knee position
  calf.position.copy(thigh.worldToLocal(solveKnee.clone()));
  root.updateMatrixWorld(true);
  // 3) rotate the calf so knee→foot (post-thigh rotation) points at the target
  const knee2 = calf.getWorldPosition(new THREE.Vector3());
  const foot2 = foot.getWorldPosition(new THREE.Vector3());
  aimBoneWorld(calf, foot2.clone().sub(knee2), clampedTarget.clone().sub(knee2));
  root.updateMatrixWorld(true);
  // 4) place the foot joint at the solved target
  foot.position.copy(calf.worldToLocal(clampedTarget.clone()));
  root.updateMatrixWorld(true);
  return true;
}

const ONE_SHOT_ANIMS: Record<string, string> = {
  kick: 'kick_run',
  handball: 'hand_pass',
  tackle: 'tackle_reach',
  mark_jump: 'catch',
  celebrate: 'celebrate_jump',
  hit_deck: 'knocked_down',
};

/** Route the kick one-shot by context: stationary players punt with a set shot,
 * runners use the on-the-run punt. Pure — exported for tests. */
export function routeOneShot(anim: string, speed: number): string {
  if (anim === 'kick') return speed < 0.8 ? 'drop_kick' : 'kick_run';
  return ONE_SHOT_ANIMS[anim] ?? '';
}

export class MotionBinding {
  readonly state = initialMotionState(0);
  private readonly actions = new Map<string, THREE.AnimationAction>();
  private readonly assets: MotionAssets;
  private readonly style: number;
  private prevFacing: number;
  private smoothedTurn = 0;
  private forcedClip: string | null = null;
  private lastSpeed = 0;
  private readonly plants: [PlantSide, PlantSide] = [createPlantSide(), createPlantSide()];
  private bones: {
    thigh: [THREE.Object3D, THREE.Object3D];
    calf: [THREE.Object3D, THREE.Object3D];
    foot: [THREE.Object3D, THREE.Object3D];
  } | null = null;

  constructor(
    mixer: THREE.AnimationMixer,
    gltf: GLTF,
    assets: MotionAssets,
    playerIndex: number,
    facing: number
  ) {
    this.assets = assets;
    this.state = initialMotionState(playerIndex);
    this.state.phase = initialPhase(playerIndex);
    this.style = gaitStyle(playerIndex);
    this.prevFacing = facing;
    for (const clip of gltf.animations) {
      const action = mixer.clipAction(clip);
      action.paused = true; // engine owns the clock
      action.clampWhenFinished = true;
      action.setLoop(THREE.LoopRepeat, Infinity);
      action.setEffectiveWeight(0);
      action.enabled = false;
      action.play(); // keep it in the mixer so weight application works
      this.actions.set(clip.name, action);
    }
  }

  /** Force a one-shot (kick, tackle, ...). Released automatically when it ends.
   * Kicks route by last-frame speed (set shot when standing, on-the-run punt otherwise). */
  forceOneShot(anim: string): void {
    const clip = routeOneShot(anim, this.lastSpeed);
    if (clip && this.actions.has(clip)) this.forcedClip = clip;
  }

  /** Foot-plant flags for audio/FX; updated every frame. */
  get footPlantedLeft(): boolean {
    return this.state.footPlantedLeft;
  }
  get footPlantedRight(): boolean {
    return this.state.footPlantedRight;
  }

  update(
    dt: number,
    p: { vx: number; vz: number; facing: number },
    ballState: BallState,
    intent: PlayerIntent,
    secondsUntilContact = -1
  ): void {
    // World → facing-root XZ (+z forward, +x right), same convention as the baker.
    const f = p.facing;
    const s = Math.sin(f);
    const c = Math.cos(f);
    const localVel = { x: p.vx * s - p.vz * c, z: p.vx * c + p.vz * s };
    const rawTurn = wrapAngle(f - this.prevFacing) / Math.max(dt, 1e-4);
    this.prevFacing = f;
    // low-pass the turn rate so single-tick angle noise doesn't thrash the search
    this.smoothedTurn += (rawTurn - this.smoothedTurn) * Math.min(1, dt * 8);

    const speed = Math.hypot(p.vx, p.vz);
    this.lastSpeed = speed;
    const forced = this.forcedClip;
    this.assets.engine.update(
      this.state, speed, -this.smoothedTurn, ballState, intent, dt,
      secondsUntilContact, 1, null, localVel, localVel, forced, this.style
    );
    // release the forced one-shot once it has finished and committed
    if (this.forcedClip) {
      const meta = this.assets.meta.get(this.state.currentClipId);
      if (!this.state.nextClipId && meta && !meta.loop && this.state.phase >= 0.999) {
        this.forcedClip = null;
      }
    }

    this.applyPose();
  }

  /**
   * Planted-foot IK (Gaelic `plantFeet`/`plantOne` port, flag-gated).
   * Call AFTER `mixer.update(dt)` and after the root's position/rotation are
   * set for this frame. Re-solves the leg so a stance foot stays anchored to
   * the ground point where it landed while the clip blends or the body
   * translates over it. Authored foot orientation is kept; only the leg chain
   * is re-aimed. No-op unless ?plantik=1.
   */
  plantIk(dt: number, root: THREE.Object3D, forwardX: number, forwardZ: number): void {
    if (!PLANT_IK_ENABLED) return;
    if (!this.bones) {
      const find = (name: string) => root.getObjectByName(name) ?? null;
      const thighL = find('thigh_l'); const thighR = find('thigh_r');
      const calfL = find('calf_l'); const calfR = find('calf_r');
      const footL = find('foot_l'); const footR = find('foot_r');
      if (!thighL || !thighR || !calfL || !calfR || !footL || !footR) return;
      this.bones = { thigh: [thighL, thighR], calf: [calfL, calfR], foot: [footL, footR] };
    }
    const legs = this.bones;
    // One-shot leg actions (kick/tackle/…) keep the authored foot — Gaelic `legBusy`.
    if (this.forcedClip || this.lastSpeed < 0.45) {
      for (const side of this.plants) { side.on = false; side.weight = 0; }
      return;
    }
    root.updateMatrixWorld(true);
    const forward = new THREE.Vector3(forwardX, 0, forwardZ);
    if (forward.lengthSq() < 1e-8) forward.set(0, 0, 1);
    forward.normalize();
    const groundY = 0.08; // foot rest height, matches Gaelic `rel.y = 0.08`
    for (let i = 0; i < 2; i++) {
      const side = this.plants[i];
      const thigh = legs.thigh[i]; const calf = legs.calf[i]; const foot = legs.foot[i];
      const hipW = thigh.getWorldPosition(new THREE.Vector3());
      const kneeW = calf.getWorldPosition(new THREE.Vector3());
      const footW = foot.getWorldPosition(new THREE.Vector3());
      updatePlantSide(side, dt, footW.y, footW);
      if (side.weight <= 0.001) continue; // nothing planted this side
      const l1 = hipW.distanceTo(kneeW);
      const l2 = kneeW.distanceTo(footW);
      if (l1 < 0.05 || l2 < 0.05) { side.on = false; side.weight = 0; continue; }
      // World anchor of the stance foot, blended in by the plant weight.
      const anchor = new THREE.Vector3(side.x, groundY, side.z);
      if (hipW.distanceTo(anchor) > (l1 + l2) * MAX_REACH_FACTOR) {
        // Out of reach: release the plant (this is the push-off).
        side.on = false;
        side.weight = 0; // spring back to the authored pose next frame
        continue;
      }
      const target = footW.clone().lerp(anchor, side.weight);
      solveLegChainWorld(thigh, calf, foot, target, forward, root);
    }
  }

  private applyPose(): void {
    const st = this.state;
    const cur = st.currentClipId;
    const nxt = st.nextClipId;
    for (const [name, action] of this.actions) {
      let weight = 0;
      if (name === cur && cur.length > 0) weight = nxt.length > 0 ? 1 - st.blendWeight : 1;
      else if (name === nxt && nxt.length > 0) weight = st.blendWeight;
      action.enabled = weight > 0.001;
      action.setEffectiveWeight(weight);
    }
    const setTime = (name: string, phase: number) => {
      if (!name) return;
      const action = this.actions.get(name);
      const meta = this.assets.meta.get(name);
      if (!action || !meta) return;
      action.time = Math.min(Math.max(phase, 0), 1) * meta.duration;
    };
    setTime(cur, st.phase);
    setTime(nxt, st.nextPhase);
  }
}
