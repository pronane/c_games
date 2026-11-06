/**
 * InputManager — keyboard + mouse, gamepads (controllers) and touch, merged
 * into one InputFrame per human player slot. Supports two players on the same
 * device (keyboard + pad, or two pads) and rumble on controllers.
 */
import {
  EdgeDetector,
  GAMEPAD_AXES,
  GAMEPAD_BUTTONS,
  GameAction,
  KEYBOARD_MAP,
  TOUCH_BUTTONS,
  TOUCH_STICK,
  applyDeadZone,
  emptyInputFrame,
  InputFrame,
  touchButtonAt,
  touchStickDelta,
} from './mappings';

export interface GamepadSnapshot {
  index: number;
  id: string;
  connected: boolean;
}

export class InputManager {
  private keys = new Set<string>();
  private keyEdges = new EdgeDetector();
  private kickWasHeld = new Set<string>();
  private touchStick: { x: number; y: number } = { x: 0, y: 0 };
  private touchActive = new Set<string>();
  private touchKickHeld = false;
  private padButtonsPrev: boolean[][] = [[], []];
  private padKickHeld: boolean[] = [false, false];
  isTouchDevice = false;
  /** Slot 0 = keyboard/gamepad0/touch; slot 1 = gamepad 1. */
  slots = 2;

  constructor(target: HTMLElement | null = null) {
    if (typeof window === 'undefined') return; // headless (tests)
    this.isTouchDevice =
      'ontouchstart' in window || (navigator.maxTouchPoints ?? 0) > 0;

    window.addEventListener('keydown', (e) => {
      if (e.code === 'Tab' || e.code === 'Space' || e.code.startsWith('Arrow')) {
        e.preventDefault();
      }
      this.keys.add(e.code);
    });
    window.addEventListener('keyup', (e) => this.keys.delete(e.code));
    window.addEventListener('blur', () => this.keys.clear());

    if (target) {
      this.bindTouch(target);
    }
    window.addEventListener('gamepadconnected', (e) => {
      // eslint-disable-next-line no-console
      console.log('[input] gamepad connected:', (e as GamepadEvent).gamepad.id);
    });
  }

  private bindTouch(target: HTMLElement): void {
    const rect = () => target.getBoundingClientRect();

    const onStart = (e: TouchEvent) => {
      e.preventDefault();
      const r = rect();
      for (const t of Array.from(e.changedTouches)) {
        const px = (t.clientX - r.left) / r.width;
        const py = (t.clientY - r.top) / r.height;
        if (px < 0.5) {
          this.touchStick = touchStickDelta(
            px, py, TOUCH_STICK.originX, TOUCH_STICK.originY, TOUCH_STICK.radius
          );
          this.touchActive.add('stick');
        } else {
          const btn = touchButtonAt(px, py);
          if (btn) {
            this.touchActive.add(btn);
            if (btn === 'kick') this.touchKickHeld = true;
          }
        }
      }
    };
    const onMove = (e: TouchEvent) => {
      e.preventDefault();
      const r = rect();
      for (const t of Array.from(e.changedTouches)) {
        const px = (t.clientX - r.left) / r.width;
        const py = (t.clientY - r.top) / r.height;
        if (px < 0.5 && this.touchActive.has('stick')) {
          this.touchStick = touchStickDelta(
            px, py, TOUCH_STICK.originX, TOUCH_STICK.originY, TOUCH_STICK.radius
          );
        }
      }
    };
    const onEnd = (e: TouchEvent) => {
      e.preventDefault();
      const r = rect();
      for (const t of Array.from(e.changedTouches)) {
        const px = (t.clientX - r.left) / r.width;
        if (px < 0.5) {
          this.touchActive.delete('stick');
          this.touchStick = { x: 0, y: 0 };
        } else {
          const btn = touchButtonAt(px, (t.clientY - r.top) / r.height);
          if (btn) {
            this.touchActive.delete(btn);
            if (btn === 'kick') this.touchKickHeld = false;
          }
        }
      }
    };

    target.addEventListener('touchstart', onStart, { passive: false });
    target.addEventListener('touchmove', onMove, { passive: false });
    target.addEventListener('touchend', onEnd, { passive: false });
    target.addEventListener('touchcancel', onEnd, { passive: false });
  }

  /** Poll everything and produce a frame for one human slot. */
  poll(slot = 0): InputFrame {
    const frame = emptyInputFrame();

    if (typeof window === 'undefined') return frame;

    // ------------------------------------------------------------- keyboard
    if (slot === 0) {
      const pressed = new Set<string>();
      for (const code of this.keys) {
        const action = KEYBOARD_MAP[code];
        if (action) pressed.add(action);
      }
      const edges = this.keyEdges.update(pressed);

      if (pressed.has('moveUp')) frame.moveZ -= 1;
      if (pressed.has('moveDown')) frame.moveZ += 1;
      if (pressed.has('moveLeft')) frame.moveX -= 1;
      if (pressed.has('moveRight')) frame.moveX += 1;
      frame.sprint = pressed.has('sprint');

      const kickNow = pressed.has('kick');
      frame.kickHeld = kickNow;
      frame.kickReleased = this.kickWasHeld.has('kb') && !kickNow;
      if (kickNow) this.kickWasHeld.add('kb');
      else this.kickWasHeld.delete('kb');

      frame.handball = edges.has('handball');
      frame.tackle = pressed.has('tackle');
      frame.switchPlayer = edges.has('switchPlayer');
      frame.bounce = edges.has('bounce');
      frame.pause = edges.has('pause');
      frame.confirm = edges.has('confirm');
      frame.back = edges.has('back');
    }

    // --------------------------------------------------------------- touch
    if (slot === 0 && this.isTouchDevice) {
      frame.moveX += this.touchStick.x;
      frame.moveZ += this.touchStick.y;
      if (this.touchActive.has('sprint')) frame.sprint = true;
      if (this.touchActive.has('handball')) frame.handball = true;
      if (this.touchActive.has('tackle')) frame.tackle = true;
      if (this.touchActive.has('switchPlayer')) frame.switchPlayer = true;
      const kickNow = this.touchKickHeld;
      frame.kickHeld = frame.kickHeld || kickNow;
      if (kickNow) this.kickWasHeld.add('touch');
      else if (this.kickWasHeld.has('touch')) {
        frame.kickReleased = true;
        this.kickWasHeld.delete('touch');
      }
    }

    // -------------------------------------------------------------- gamepad
    const pads = typeof navigator !== 'undefined' && navigator.getGamepads
      ? navigator.getGamepads()
      : [];
    const padIndex = slot;
    const pad = pads[padIndex];
    if (pad && pad.connected) {
      const stick = applyDeadZone(pad.axes[GAMEPAD_AXES.moveX] ?? 0, pad.axes[GAMEPAD_AXES.moveY] ?? 0);
      frame.moveX += stick.x;
      frame.moveZ += stick.y;
      const aim = applyDeadZone(pad.axes[GAMEPAD_AXES.aimZ] ?? 0, 0);
      frame.aimZ = aim.x;

      const prev = this.padButtonsPrev[padIndex] ?? [];
      const now = pad.buttons.map((b) => b.pressed);
      this.padButtonsPrev[padIndex] = now;

      for (const [idxStr, action] of Object.entries(GAMEPAD_BUTTONS)) {
        const idx = Number(idxStr);
        const down = now[idx] ?? false;
        const wasDown = prev[idx] ?? false;
        switch (action as GameAction) {
          case 'kick':
            frame.kickHeld = frame.kickHeld || down;
            if (this.padKickHeld[padIndex] && !down) {
              frame.kickReleased = true;
              this.padKickHeld[padIndex] = false;
            }
            if (down) this.padKickHeld[padIndex] = true;
            break;
          case 'sprint':
            frame.sprint = frame.sprint || down;
            break;
          case 'tackle':
            frame.tackle = frame.tackle || down;
            break;
          case 'handball':
            if (down && !wasDown) frame.handball = true;
            break;
          case 'switchPlayer':
            if (down && !wasDown) frame.switchPlayer = true;
            break;
          case 'bounce':
            if (down && !wasDown) frame.bounce = true;
            break;
          case 'pause':
            if (down && !wasDown) frame.pause = true;
            break;
          case 'confirm':
            if (down && !wasDown) frame.confirm = true;
            break;
          case 'back':
            if (down && !wasDown) frame.back = true;
            break;
          case 'moveUp':
            if (down) frame.moveZ -= 1;
            break;
          case 'moveDown':
            if (down) frame.moveZ += 1;
            break;
          case 'moveLeft':
            if (down) frame.moveX -= 1;
            break;
          case 'moveRight':
            if (down) frame.moveX += 1;
            break;
        }
      }
    }

    const mag = Math.hypot(frame.moveX, frame.moveZ);
    if (mag > 1) {
      frame.moveX /= mag;
      frame.moveZ /= mag;
    }
    return frame;
  }

  connectedPads(): GamepadSnapshot[] {
    const pads = typeof navigator !== 'undefined' && navigator.getGamepads
      ? navigator.getGamepads()
      : [];
    return pads
      .filter((p): p is Gamepad => !!p && p.connected)
      .map((p) => ({ index: p.index, id: p.id, connected: true }));
  }

  /** Rumble a controller (if it supports it) and/or vibrate the device. */
  rumble(slot: number, strong: number, weak: number, durationMs: number): void {
    if (typeof window === 'undefined') return;
    const pads = navigator.getGamepads ? navigator.getGamepads() : [];
    const pad = pads[slot];
    if (pad) {
      const actuator = (pad as Gamepad & { vibrationActuator?: { playEffect: (t: string, a: object) => Promise<unknown> } }).vibrationActuator;
      if (actuator?.playEffect) {
        actuator.playEffect('dual-rumble', {
          duration: durationMs,
          strongMagnitude: strong,
          weakMagnitude: weak,
        }).catch(() => undefined);
      }
    }
    if (this.isTouchDevice && 'vibrate' in navigator) {
      navigator.vibrate(Math.round(durationMs / 2));
    }
  }
}

export { TOUCH_BUTTONS };
