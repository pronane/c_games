/**
 * Input mappings — the pure, device-agnostic action layer.
 *
 * Every device (keyboard, mouse, gamepad, touch) resolves to the same set of
 * game actions, so the game plays identically everywhere. These functions are
 * pure and fully unit-tested.
 */

export type GameAction =
  | 'moveUp' | 'moveDown' | 'moveLeft' | 'moveRight'
  | 'kick' | 'handball' | 'tackle' | 'switchPlayer' | 'sprint' | 'bounce'
  | 'pause' | 'confirm' | 'back' | 'camera' | 'toggleMarkers';

/** Keyboard: code → action (KeyboardEvent.code values). */
export const KEYBOARD_MAP: Record<string, GameAction> = {
  KeyW: 'moveUp',
  ArrowUp: 'moveUp',
  KeyS: 'moveDown',
  ArrowDown: 'moveDown',
  KeyA: 'moveLeft',
  ArrowLeft: 'moveLeft',
  KeyD: 'moveRight',
  ArrowRight: 'moveRight',
  Space: 'kick',
  KeyE: 'handball',
  KeyF: 'tackle',
  KeyQ: 'switchPlayer',
  Tab: 'switchPlayer',
  ShiftLeft: 'sprint',
  ShiftRight: 'sprint',
  KeyB: 'bounce',
  Escape: 'pause',
  Enter: 'confirm',
  Backspace: 'back',
  KeyC: 'camera',
  KeyV: 'toggleMarkers',
};

/** Gamepad standard mapping: button index → action. */
export const GAMEPAD_BUTTONS: Record<number, GameAction> = {
  0: 'kick',        // A / Cross
  1: 'handball',    // B / Circle
  2: 'tackle',      // X / Square
  3: 'switchPlayer',// Y / Triangle
  4: 'bounce',      // LB / L1
  5: 'sprint',      // RB / R1
  7: 'sprint',      // RT / R2
  9: 'pause',       // Start / Options
  8: 'back',        // Back / Select
  12: 'moveUp',     // dpad
  13: 'moveDown',
  14: 'moveLeft',
  15: 'moveRight',
};

export const GAMEPAD_DEADZONE = 0.22;
export const GAMEPAD_AXES = { moveX: 0, moveY: 1, aimZ: 2 };

/** Apply a radial dead zone to a stick axis pair. */
export function applyDeadZone(
  x: number,
  y: number,
  deadzone = GAMEPAD_DEADZONE
): { x: number; y: number } {
  const mag = Math.hypot(x, y);
  if (mag <= deadzone) return { x: 0, y: 0 };
  const scaled = Math.min(1, (mag - deadzone) / (1 - deadzone));
  return { x: (x / mag) * scaled, y: (y / mag) * scaled };
}

export interface TouchButtonLayout {
  kick: { x: number; y: number; r: number };
  handball: { x: number; y: number; r: number };
  tackle: { x: number; y: number; r: number };
  sprint: { x: number; y: number; r: number };
  switchPlayer: { x: number; y: number; r: number };
}

/** Touch buttons (fractions of screen size) — big, thumb-friendly targets. */
export const TOUCH_BUTTONS: TouchButtonLayout = {
  kick: { x: 0.87, y: 0.72, r: 0.085 },
  handball: { x: 0.72, y: 0.82, r: 0.075 },
  tackle: { x: 0.87, y: 0.9, r: 0.075 },
  sprint: { x: 0.72, y: 0.63, r: 0.065 },
  switchPlayer: { x: 0.62, y: 0.72, r: 0.055 },
};

/** Virtual joystick: the left 45% of the screen is the movement stick. */
export const TOUCH_STICK = { originX: 0.16, originY: 0.72, radius: 0.16 };

export function touchStickDelta(
  px: number,
  py: number,
  ox: number,
  oy: number,
  radius: number
): { x: number; y: number } {
  const dx = (px - ox) / radius;
  const dy = (py - oy) / radius;
  const mag = Math.hypot(dx, dy);
  if (mag > 1) return { x: dx / mag, y: dy / mag };
  return { x: dx, y: dy };
}

export function touchButtonAt(
  px: number,
  py: number
): keyof TouchButtonLayout | null {
  let best: keyof TouchButtonLayout | null = null;
  let bestD = Infinity;
  for (const key of Object.keys(TOUCH_BUTTONS) as (keyof TouchButtonLayout)[]) {
    const b = TOUCH_BUTTONS[key];
    const d = Math.hypot(px - b.x, py - b.y);
    if (d <= b.r && d < bestD) {
      best = key;
      bestD = d;
    }
  }
  return best;
}

/** Edge detector: true only on the frame an action transitions to pressed. */
export class EdgeDetector {
  private prev = new Set<string>();

  update(currently: Set<string>): Set<string> {
    const edges = new Set<string>();
    for (const k of currently) {
      if (!this.prev.has(k)) edges.add(k);
    }
    this.prev = new Set(currently);
    return edges;
  }
}

export interface InputFrame {
  moveX: number;
  moveZ: number;
  sprint: boolean;
  kickHeld: boolean;
  kickReleased: boolean;
  handball: boolean;
  tackle: boolean;
  switchPlayer: boolean;
  bounce: boolean;
  pause: boolean;
  confirm: boolean;
  back: boolean;
  camera: boolean;
  toggleMarkers: boolean;
  aimZ: number;
}

export function emptyInputFrame(): InputFrame {
  return {
    moveX: 0, moveZ: 0, sprint: false,
    kickHeld: false, kickReleased: false,
    handball: false, tackle: false, switchPlayer: false, bounce: false,
    pause: false, confirm: false, back: false,
    camera: false, toggleMarkers: false,
    aimZ: 0,
  };
}
