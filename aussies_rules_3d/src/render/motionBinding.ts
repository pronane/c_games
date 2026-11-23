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

function wrapAngle(a: number): number {
  while (a > Math.PI) a -= 2 * Math.PI;
  while (a < -Math.PI) a += 2 * Math.PI;
  return a;
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
