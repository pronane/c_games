import { emptyHumanIntent, type HumanIntent } from './match';
/** Fixed tick input trace, shared by CI browser capture and simulation tests. */
export function captureIntent(tick: number): HumanIntent {
  const h = emptyHumanIntent();
  const phase = Math.floor(tick / 180) % 6;
  // Straight run, right-angle cut, reversal, stop/dispose, and selection changes.
  const directions = [[1, 0], [0, 1], [-1, 0], [0, 0], [0, -1], [1, 0]];
  [h.moveX, h.moveZ] = directions[phase];
  h.sprint = phase < 3;
  h.kickHeld = phase === 3 && tick % 180 < 30;
  h.kickReleased = phase === 3 && tick % 180 === 30;
  h.handball = tick % 600 === 420;
  h.switchPlayer = tick % 600 === 0;
  h.tackle = tick % 240 === 120;
  return h;
}
