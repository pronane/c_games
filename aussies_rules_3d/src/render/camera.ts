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
 */
import * as THREE from 'three';
import { FIELD, MatchState } from '../rules/types';
import { attackGoalX } from '../rules/field';

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

  constructor(camera: THREE.PerspectiveCamera) {
    this.camera = camera;
    this.camera.position.set(-26, 19, 46);
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

  update(dt: number, state: MatchState, controlledX: number, controlledZ: number): void {
    const b = state.ball;
    this.target.set(b.x, Math.max(0, b.y), b.z);
    const ballSpeed = Math.hypot(b.vx ?? 0, b.vz ?? 0);
    if (ballSpeed > 2) {
      this.chaseDir.set(b.vx, b.vz).normalize();
    }
    const dirX = this.chaseDir.x;
    const dirZ = this.chaseDir.y;

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
        b.x - dirX * 30,
        34,
        b.z - dirZ * 30
      );
      this.lookAt.lerp(new THREE.Vector3(b.x, 0.5, b.z), Math.min(1, dt * 2.6));
    } else if (this.view === 'tactical') {
      // near top-down — the whole shape at once
      const cx = b.x * 0.55;
      const cz = b.z * 0.55;
      this.desired.set(cx, 88, cz + 3);
      this.lookAt.lerp(new THREE.Vector3(cx, 0, cz), Math.min(1, dt * 3.4));
    } else {
      // broadcast (default): tight TV shot — players are big enough to read
      const leadX = (b.vx ?? 0) * 0.55;
      const leadZ = (b.vz ?? 0) * 0.55;
      this.desired.set(
        b.x * 0.85 + leadX * 0.6 - 3.5,
        17.5 + Math.abs(b.z) * 0.045,
        Math.max(42, 47 - Math.abs(b.z) * 0.09)
      );
      this.lookAt.lerp(
        new THREE.Vector3(b.x + leadX, 1.4, b.z + leadZ),
        Math.min(1, dt * 2.8)
      );
    }

    const ease = this.mode === 'broadcast' ? 2.6 : 1.6;
    this.camera.position.lerp(this.desired, Math.min(1, dt * ease));
    void controlledX;
    void controlledZ;
    this.camera.lookAt(this.lookAt);
  }

  /** Slight zoom toward goal for set shots. */
  focusGoal(team: 0 | 1): void {
    void team;
    this.setMode('setShot');
  }
}
