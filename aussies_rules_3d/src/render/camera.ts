/**
 * Broadcast camera — the elevated wing view used in TV footy, with smooth
 * tracking, a set-shot behind-the-kick view and goal celebration orbits.
 */
import * as THREE from 'three';
import { FIELD, MatchState } from '../rules/types';
import { attackGoalX } from '../rules/field';

export type CameraMode = 'broadcast' | 'setShot' | 'celebration' | 'menu';

export class BroadcastCamera {
  camera: THREE.PerspectiveCamera;
  mode: CameraMode = 'broadcast';
  private target = new THREE.Vector3();
  private desired = new THREE.Vector3();
  private lookAt = new THREE.Vector3();
  private celebrationT = 0;

  constructor(camera: THREE.PerspectiveCamera) {
    this.camera = camera;
    this.camera.position.set(-40, 32, 92);
    this.lookAt.set(0, 0, 0);
  }

  setMode(mode: CameraMode): void {
    if (this.mode !== mode) {
      this.celebrationT = 0;
      this.mode = mode;
    }
  }

  update(dt: number, state: MatchState, controlledX: number, controlledZ: number): void {
    const b = state.ball;
    this.target.set(b.x, Math.max(0, b.y), b.z);

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
    } else {
      // broadcast: high on the wing, tracks the ball with lead
      const leadX = (b.vx ?? 0) * 0.85;
      const leadZ = (b.vz ?? 0) * 0.85;
      const zoom = THREE.MathUtils.clamp(52 - Math.abs(b.z) * 0.14, 38, 56);
      this.desired.set(
        b.x * 0.82 + leadX * 0.7 - 6,
        26 + Math.abs(b.z) * 0.06,
        Math.max(60, zoom + 34) * (this.camera.position.z >= 0 ? 1 : -1)
      );
      // don't flip sides: keep camera on the near wing (positive z)
      this.desired.z = Math.abs(this.desired.z);
      this.lookAt.lerp(
        new THREE.Vector3(b.x + leadX, 1.5, b.z + leadZ),
        Math.min(1, dt * 2.6)
      );
    }

    const ease = this.mode === 'broadcast' ? 2.4 : 1.6;
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
