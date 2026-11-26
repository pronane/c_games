/**
 * Broadcast camera — multiple switchable views on top of the classic high wing
 * shot, with smooth tracking, set-shot and goal-celebration modes.
 *
 * Views (cycle with C / L3 / R3):
 *   broadcast — tight TV shot, tracks the ball (players are big enough to read)
 *   wing      — the classic high wing view (what you get on Fox footy)
 *   behind    — low chase cam behind the play
 *   aerial    — high chase, behind and above the ball
 *   tactical  — near top-down view of the whole shape
 *
 * The broadcast shot frames dynamically: it widens for spread play, long
 * kicks and restarts, and tightens for contests — the openness model from the
 * gaelic_football_3d broadcast work. Mouse-wheel zoom nudges it and recentres
 * after 3 s idle.
 */
import * as THREE from 'three';
import { FIELD, MatchState } from '../rules/types';
import { attackGoalX } from '../rules/field';
import { enforceFraming, SAFE_MARGIN, type FitSubject } from './framing';

export type CameraMode = 'broadcast' | 'setShot' | 'celebration' | 'menu';
export type ViewName = 'broadcast' | 'wing' | 'behind' | 'aerial' | 'tactical';

export const VIEW_ORDER: ViewName[] = ['broadcast', 'wing', 'behind', 'aerial', 'tactical'];

const VIEW_LABEL: Record<ViewName, string> = {
  broadcast: 'BROADCAST',
  wing: 'WING',
  behind: 'CHASE',
  aerial: 'AERIAL',
  tactical: 'TACTICAL',
};

export class BroadcastCamera {
  camera: THREE.PerspectiveCamera;
  mode: CameraMode = 'broadcast';
  view: ViewName = 'broadcast';
  private target = new THREE.Vector3();
  private desired = new THREE.Vector3();
  private lookAt = new THREE.Vector3();
  private celebrationT = 0;
  private chaseDir = new THREE.Vector2(1, 0);
  private openness = 0.12;
  private heldDistance = 0;
  private fitHold = 0;
  private shotKey = '';
  private renderedAim = new THREE.Vector3(0, 1, 0);
  readonly diagnostics = { emergencyCorrections: 0, playerExcluded: false };
  private zoomOffset = 0;
  private zoomIdleT = 0;

  constructor(camera: THREE.PerspectiveCamera) {
    this.camera = camera;
    this.camera.position.set(-26, 24, FIELD.boundaryB + 23);
    this.lookAt.set(0, 1, 0);
  }

  setMode(mode: CameraMode): void {
    if (this.mode !== mode) {
      this.celebrationT = 0;
      this.mode = mode;
    }
  }

  /** Cycle to the next user-selectable view. Returns the new view's label. */
  cycleView(): string {
    const i = VIEW_ORDER.indexOf(this.view);
    this.view = VIEW_ORDER[(i + 1) % VIEW_ORDER.length];
    return VIEW_LABEL[this.view];
  }

  viewLabel(): string {
    return VIEW_LABEL[this.view];
  }

  /** Mouse-wheel zoom nudge. Positive zooms out (open), negative tightens. */
  addZoom(delta: number): void {
    this.zoomOffset = THREE.MathUtils.clamp(this.zoomOffset + delta, -0.42, 0.55);
    this.zoomIdleT = 0;
  }

  /**
   * `controlled` — the player on your stick (null while spectating/attract or
   * when no live controlled player exists). The framing post-step keeps the
   * ball inside a safe NDC box; nearby selection is a secondary planning subject.
   * See framing.ts. Celebration mode is exempt (cinematic orbit).
   */
  update(
    dt: number,
    state: MatchState,
    controlled: { x: number; y: number; z: number } | null = null
  ): void {
    const b = state.ball;
    this.target.set(b.x, Math.max(0, b.y), b.z);
    const ballSpeed = Math.hypot(b.vx ?? 0, b.vz ?? 0);
    if (ballSpeed > 2) {
      this.chaseDir.set(b.vx, b.vz).normalize();
    }
    const dirX = this.chaseDir.x;
    const dirZ = this.chaseDir.y;

    // --- dynamic framing: how spread / aerial / restart-ish is the play?
    this.zoomIdleT += dt;
    if (this.zoomIdleT > 3) this.zoomOffset *= Math.exp(-dt * 1.5);
    {
      const d2: number[] = [];
      for (const p of state.players) {
        if (p.onBench) continue;
        d2.push((p.x - b.x) ** 2 + (p.z - b.z) ** 2);
      }
      d2.sort((a, c) => a - c);
      let sum = 0;
      const n = Math.min(6, d2.length);
      for (let i = 0; i < n; i++) sum += Math.sqrt(d2[i]);
      const spread = Math.min(1, n > 0 ? sum / n / 26 : 0);
      const flight =
        Math.min(1, Math.max(0, (ballSpeed - 5) / 20)) * 0.4 + (b.y > 2.6 ? 0.18 : 0);
      const ph = state.phase;
      const restart =
        ph === 'kickIn' || ph === 'centreBallUp' || ph === 'ballUp' || ph === 'throwIn'
          ? 0.42
          : ph === 'freeKick'
            ? 0.18
            : 0;
      const target = THREE.MathUtils.clamp(spread * 0.45 + flight + restart + this.zoomOffset, 0, 1.15);
      this.openness += (target - this.openness) * Math.min(1, dt * 1.9);
    }

    if (this.mode === 'celebration') {
      this.celebrationT += dt;
      const side = b.x > 0 ? 1 : -1;
      const gx = side * FIELD.goalLineX;
      const ang = this.celebrationT * 0.5;
      this.desired.set(
        gx - side * 26 + Math.sin(ang) * 18,
        14 + Math.sin(this.celebrationT * 0.8) * 2,
        Math.cos(ang) * 26
      );
      this.lookAt.lerp(new THREE.Vector3(gx - side * 10, 3, 0), Math.min(1, dt * 2.4));
    } else if (this.mode === 'setShot') {
      const goalX = attackGoalX(state.freeKick?.team ?? 0);
      const dir = Math.sign(goalX - b.x) || 1;
      this.desired.set(
        b.x - dir * 16,
        9.5,
        b.z * 0.7 + 12
      );
      this.lookAt.lerp(new THREE.Vector3(goalX, 2, 0), Math.min(1, dt * 1.6));
    } else if (this.view === 'wing') {
      // classic high wing: far out, follows the ball with lead
      const leadX = (b.vx ?? 0) * 0.85;
      const leadZ = (b.vz ?? 0) * 0.85;
      const zoom = THREE.MathUtils.clamp(52 - Math.abs(b.z) * 0.14, 38, 56);
      this.desired.set(
        b.x * 0.82 + leadX * 0.7 - 6,
        26 + Math.abs(b.z) * 0.06,
        Math.max(60, zoom + 34) * (this.camera.position.z >= 0 ? 1 : -1)
      );
      this.desired.z = Math.abs(this.desired.z);
      this.lookAt.lerp(
        new THREE.Vector3(b.x + leadX, 1.5, b.z + leadZ),
        Math.min(1, dt * 2.6)
      );
    } else if (this.view === 'behind') {
      // low chase behind the flight of the ball
      this.desired.set(
        b.x - dirX * 15.5,
        8.5,
        b.z - dirZ * 15.5
      );
      this.lookAt.lerp(new THREE.Vector3(b.x + dirX * 14, 1.3, b.z + dirZ * 14), Math.min(1, dt * 3.2));
    } else if (this.view === 'aerial') {
      // high chase — reads the whole contest
      this.desired.set(
        b.x - dirX * (26 + this.openness * 8),
        30 + this.openness * 11,
        b.z - dirZ * (26 + this.openness * 8)
      );
      this.lookAt.lerp(new THREE.Vector3(b.x, 0.5, b.z), Math.min(1, dt * 2.6));
    } else if (this.view === 'tactical') {
      // near top-down — the whole shape at once
      const cx = b.x * 0.55;
      const cz = b.z * 0.55;
      this.desired.set(cx, 88, cz + 3);
      this.lookAt.lerp(new THREE.Vector3(cx, 0, cz), Math.min(1, dt * 3.4));
    } else {
      // broadcast (default): tight TV shot — widens when the play is spread
      const leadX = (b.vx ?? 0) * 0.55;
      const leadZ = (b.vz ?? 0) * 0.55;
      const o = this.openness;
      this.desired.set(
        b.x * 0.86 + leadX * 0.6 - 4,
        13.5 + o * 17 + Math.abs(b.z) * 0.045,
        Math.max(FIELD.boundaryB + 12, b.z + 24)
      );
      this.lookAt.lerp(
        new THREE.Vector3(b.x + leadX, 1.4, b.z + leadZ),
        Math.min(1, dt * 2.8)
      );
    }

    // Plan a conservative fit BEFORE easing. The live ball has priority;
    // distant selection is represented by the existing offscreen arrow.
    const subjects: FitSubject[] = [
      { x: b.x, y: Math.max(b.y, 0.15), z: b.z, weight: 1.3 },
      { x: b.x, y: 0.15, z: b.z, weight: 1 },
    ];
    // Do not tilt up into the stands just to centre a high ball.
    if (this.mode !== 'celebration') this.desired.y = Math.max(this.desired.y, b.y + 12);
    const nearby = controlled && Math.hypot(controlled.x - b.x, controlled.z - b.z) < 22;
    this.diagnostics.playerExcluded = !!controlled && !nearby;
    if (nearby && controlled) subjects.push(controlled);
    // Remain on the TV side of the touchline, using a damped lens to retain
    // action scale at the far side rather than driving inside the near wing.
    const range = Math.max(1, this.desired.distanceTo(this.target));
    const lens = this.mode === 'broadcast' && this.view === 'broadcast'
      ? THREE.MathUtils.clamp(THREE.MathUtils.radToDeg(2 * Math.atan((22 + this.openness * 8) / range)), 24, 52)
      : 46;
    if (Math.abs(lens - this.camera.fov) > 0.35) {
      this.camera.fov += (lens - this.camera.fov) * (1 - Math.exp(-dt * 1.6));
      this.camera.updateProjectionMatrix();
    }
    if (this.mode !== 'celebration') {
      const plan = enforceFraming(this.desired, this.lookAt, this.camera.fov, this.camera.aspect, subjects, 0.60);
      if (plan) { this.desired.copy(plan.position); this.lookAt.copy(plan.lookAt); }
    }
    const key = `${this.mode}:${this.view}`;
    if (key !== this.shotKey) { this.heldDistance = 0; this.fitHold = 0; this.shotKey = key; }
    const ray = this.desired.clone().sub(this.lookAt);
    const requested = ray.length();
    if (requested > this.heldDistance) { this.heldDistance = requested; this.fitHold = 0.8; }
    else {
      this.fitHold = Math.max(0, this.fitHold - dt);
      if (!this.fitHold) this.heldDistance += (requested - this.heldDistance) * (1 - Math.exp(-dt * 0.7));
    }
    if (requested > 0.001) this.desired.copy(this.lookAt).addScaledVector(ray, this.heldDistance / requested);
    const alpha = 1 - Math.exp(-dt * 3.2);
    this.camera.position.lerp(this.desired, alpha);
    this.renderedAim.lerp(this.lookAt, alpha);
    // Emergency recovery includes ball and ground context, never distant selection.
    // Ordinary travel uses the wider predictive planning region above.
    if (this.mode !== 'celebration') {
      const emergency = enforceFraming(this.camera.position, this.renderedAim,
        this.camera.fov, this.camera.aspect, subjects.slice(0, 2), SAFE_MARGIN);
      if (emergency) {
        this.camera.position.copy(emergency.position);
        this.renderedAim.copy(emergency.lookAt);
        this.diagnostics.emergencyCorrections++;
      }
    }
    this.camera.lookAt(this.renderedAim);
  }

  /** Slight zoom toward goal for set shots. */
  focusGoal(team: 0 | 1): void {
    void team;
    this.setMode('setShot');
  }
}
