/** Controller units: metres, seconds, radians. Presentation consumes this heading. */
export function angleDelta(to: number, from: number): number {
  return Math.atan2(Math.sin(to - from), Math.cos(to - from));
}
export function stepLocomotion(
  p: { vx: number; vz: number; facing: number }, mx: number, mz: number,
  maxSpeed: number, dt: number
): void {
  const mag = Math.hypot(mx, mz);
  const speed = Math.hypot(p.vx, p.vz);
  const heading = mag > 0.05 ? Math.atan2(mz, mx) : p.facing;
  const error = angleDelta(heading, p.facing);
  const turnLimit = (speed > 3 ? 2.8 : 7) * dt;
  p.facing += Math.max(-turnLimit, Math.min(turnLimit, error));
  // Brake before reversing: a forward run cannot accelerate through a 180° pivot.
  const alignment = Math.max(0, Math.cos(angleDelta(heading, p.facing)));
  const targetSpeed = mag > 0.05 ? maxSpeed * Math.min(1, mag) * alignment * alignment : 0;
  const tx = Math.cos(p.facing) * targetSpeed;
  const tz = Math.sin(p.facing) * targetSpeed;
  const dx = tx - p.vx, dz = tz - p.vz;
  const distance = Math.hypot(dx, dz);
  const acceleration = targetSpeed < speed ? 12 : 7;
  const step = Math.min(1, acceleration * dt / Math.max(distance, 1e-8));
  p.vx += dx * step;
  p.vz += dz * step;
}

/** Shipped squad asset forward convention; shared by creation and frame updates. */
export function playerModelYaw(facing: number): number { return -facing - Math.PI / 2; }
