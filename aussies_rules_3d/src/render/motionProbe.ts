/** Runtime measurements, not a visual-quality score. All values use world metres/seconds. */
export interface FootObservation { x: number; y: number; z: number; contact: boolean }
export class MotionProbe {
  private id = -1;
  private previous: FootObservation[] = [];
  private backwardsSeconds = 0;
  private slipSum = 0;
  private slipSamples = 0;
  private samples = 0;
  private maxBackwardsSeconds = 0;
  private maxContactFootSpeed = 0;
  observe(id: number, velocity: { x: number; z: number }, forward: { x: number; z: number }, feet: FootObservation[], dt: number): void {
    if (id !== this.id) { this.previous = []; this.backwardsSeconds = 0; this.id = id; }
    if (!(dt > 0) || !Number.isFinite(dt)) return;
    this.samples++;
    const speed = Math.hypot(velocity.x, velocity.z);
    const backwards = speed > 3 && velocity.x * forward.x + velocity.z * forward.z < 0;
    this.backwardsSeconds = backwards ? this.backwardsSeconds + dt : 0;
    this.maxBackwardsSeconds = Math.max(this.maxBackwardsSeconds, this.backwardsSeconds);
    feet.forEach((foot, i) => {
      const old = this.previous[i];
      if (foot.contact && old?.contact) {
        const speed = Math.hypot(foot.x - old.x, foot.y - old.y, foot.z - old.z) / dt;
        this.slipSum += speed; this.slipSamples++;
        this.maxContactFootSpeed = Math.max(this.maxContactFootSpeed, speed);
      }
    });
    this.previous = feet.map(f => ({ ...f }));
  }
  snapshot() {
    return { samples: this.samples, maxBackwardsSeconds: this.maxBackwardsSeconds,
      contactFootSamples: this.slipSamples,
      meanContactFootSpeed: this.slipSamples ? this.slipSum / this.slipSamples : null,
      maxContactFootSpeed: this.slipSamples ? this.maxContactFootSpeed : null };
  }
}
