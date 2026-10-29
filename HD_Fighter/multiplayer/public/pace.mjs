// Wall-clock budget for the lockstep sim. Frame numbers stay contiguous;
// this only decides how many of those frames may run on this render.

export const FRAME_MS = 1000 / 60;
export const RESYNC_BEHIND = 6;
// Quiet links stay near 2–8 frames. A 120 ms hop on both sides is ~240 ms
// from one player to the other (a full ping RTT, not half of it). 36 frames
// is 600 ms, above that path plus a dropped packet.
export const MAX_DELAY_FRAMES = 36;
// Each packet carries the unacked frames, capped. A long delay still has to
// include frame 0, so the cap keeps the oldest frames, not only the newest.
export const REDUNDANT_FRAMES = 32;
const DROP_SLACK_MS = 34;

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
  let jitter = Math.max(...nets.map((n) => n.jitter || 0));
  const samples = Math.max(...nets.map((n) => Number(n.samples) || 0));
  // One or two pings cannot see jitter. A quarter of the RTT stands in
  // until there is a real spread, so a ±30 ms hop is not given the average.
  if (samples < 4) jitter = Math.max(jitter, rtt * 0.25);
  // A→server→B is each side's one-way, which is (rttA + rttB) / 2.
  // Using only max(rtt)/2 misses the second hop and the sim runs late.
  const oneWay = nets.reduce((sum, n) => sum + n.rtt / 2, 0);
  const needMs = oneWay + jitter + DROP_SLACK_MS;
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
  if (out.length <= limit) return out;
  const head = out.slice(0, Math.max(1, limit - 8));
  const tail = out.slice(out.length - 8);
  const seen = new Set();
  const merged = [];
  for (const row of head.concat(tail)) {
    if (seen.has(row.frame)) continue;
    seen.add(row.frame);
    merged.push(row);
  }
  merged.sort((a, b) => a.frame - b.frame);
  return merged;
}
