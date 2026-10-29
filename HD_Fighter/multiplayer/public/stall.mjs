// Stall follows silence from the peer, not how far the sim is behind the clock.
// A slow link that still delivers packets stays quiet. Packets resume → ok.

export const SLOW_MS = 1000;
export const LOST_MS = 9000;
export const CONNECT_TIMEOUT_MS = 4000;
export const BACKOFF_MIN_MS = 300;
export const BACKOFF_MAX_MS = 3000;
export const RECONNECT_HOLD_MS = 30000;
export const POOR_FPS = 45;
export const POOR_WINDOW_MS = 2000;

// attempt 0 → ~300 ms, then ×1.5, capped at 3 s, with ±20% jitter.
export function nextBackoff(attempt, rand = Math.random) {
  const n = Math.max(0, attempt | 0);
  const base = Math.min(BACKOFF_MAX_MS, Math.round(BACKOFF_MIN_MS * (1.5 ** n)));
  const swing = (rand() - 0.5) * 2 * base * 0.2;
  return Math.max(BACKOFF_MIN_MS, Math.round(base + swing));
}

// Heartbeats do not count. A fight stall is silence of inputs, hashes, or acks.
export function isGameData(msg) {
  if (!msg || typeof msg.t !== 'string') return false;
  if (msg.t === 'hash') return true;
  if (msg.t !== 'input') return false;
  if (typeof msg.ack === 'number') return true;
  if (typeof msg.base === 'number' && Array.isArray(msg.bits) && msg.bits.length) return true;
  if (Array.isArray(msg.batch) && msg.batch.length) return true;
  if (typeof msg.frame === 'number') return true;
  return false;
}

// True once a 2 s window of sim steps is slower than ~45 fps.
export function poorLink(stepTimes, now, windowMs = POOR_WINDOW_MS, minFps = POOR_FPS) {
  if (!stepTimes || !stepTimes.length) return false;
  if (now - stepTimes[0] < windowMs) return false;
  const cutoff = now - windowMs;
  let n = 0;
  for (let i = 0; i < stepTimes.length; i++) if (stepTimes[i] >= cutoff) n += 1;
  return n / (windowMs / 1000) < minFps;
}

export function evalStall(lastRx, now) {
  if (lastRx == null || now == null) return 'ok';
  const gap = now - lastRx;
  if (gap >= LOST_MS) return 'lost';
  if (gap >= SLOW_MS) return 'slow';
  return 'ok';
}

export function stallLabel(level) {
  if (level === 'slow') return 'Connection slow';
  if (level === 'lost') return 'Connection lost';
  return '';
}

// A refused TCP connection is the only "can't reach". An HTTP status
// (503 from a process that is still waking) keeps retrying.
export function connectFailure({ networkError = false } = {}) {
  if (networkError) {
    return { text: "Can't reach the server.", waking: false, clearPill: true };
  }
  return { text: 'Waking the server...', waking: true, clearPill: false };
}
