// Stall follows silence from the peer, not how far the sim is behind the clock.
// A slow link that still delivers packets stays quiet. Packets resume → ok.

export const SLOW_MS = 1000;
export const LOST_MS = 9000;

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
