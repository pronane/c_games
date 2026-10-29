// Wall-clock budget for the lockstep sim. Frame numbers stay contiguous;
// this only decides how many of those frames may run on this render.

export const FRAME_MS = 1000 / 60;
export const RESYNC_BEHIND = 6;
// A quiet link stays in the 2–8 frame range (~30–130 ms). A 120 ms-per-leg
// path is ~240 ms one way, so the cap has to sit above that or lockstep
// cannot tick at 60 Hz. 24 frames is 400 ms.
export const MAX_DELAY_FRAMES = 24;
// Must cover every input still waiting for an ack. At a 480 ms RTT that is
// ~30 frames; 48 leaves room for a dropped packet to be repeated.
export const REDUNDANT_FRAMES = 48;
const DELAY_MARGIN_MS = 30;

export function createPacer(now = 0) {
  return { origin: now };
}

// Never more than one frame per 1/60 s, except a short catch-up of 2
// when the sim is a few frames behind. A larger gap resets the clock
// instead of fast-forwarding the round.
export function stepBudget(pacer, simFrame, now) {
  const elapsed = now - pacer.origin;
  const ideal = Math.max(0, Math.floor(elapsed / FRAME_MS));
  let behind = ideal - simFrame;
  if (behind > RESYNC_BEHIND) {
    pacer.origin = now - simFrame * FRAME_MS;
    return 0;
  }
  if (behind <= 0) return 0;
  if (behind === 1) return 1;
  return 2;
}

export function chooseDelay(net0, net1) {
  const nets = [net0, net1].filter((n) => n && typeof n.rtt === 'number');
  if (!nets.length) return 3;
  const rtt = Math.max(...nets.map((n) => n.rtt));
  const jitter = Math.max(...nets.map((n) => n.jitter || 0));
  const needMs = rtt / 2 + jitter + DELAY_MARGIN_MS;
  let frames = Math.ceil(needMs / FRAME_MS);
  if (frames < 2) frames = 2;
  if (frames > MAX_DELAY_FRAMES) frames = MAX_DELAY_FRAMES;
  return frames;
}

export function redundantBatch(log, ack, limit = REDUNDANT_FRAMES) {
  const out = [];
  for (let i = 0; i < log.length; i++) {
    if (log[i].frame > ack) out.push(log[i]);
  }
  if (out.length > limit) return out.slice(out.length - limit);
  return out;
}
