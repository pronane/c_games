import { describe, expect, it } from 'vitest';
import {
  applyDeadZone,
  EdgeDetector,
  emptyInputFrame,
  GAMEPAD_BUTTONS,
  GAMEPAD_DEADZONE,
  KEYBOARD_MAP,
  touchButtonAt,
  touchStickDelta,
  TOUCH_BUTTONS,
} from '../src/input/mappings';

describe('keyboard mapping', () => {
  it('maps movement to both WASD and arrow keys', () => {
    expect(KEYBOARD_MAP.KeyW).toBe('moveUp');
    expect(KEYBOARD_MAP.ArrowUp).toBe('moveUp');
    expect(KEYBOARD_MAP.KeyA).toBe('moveLeft');
    expect(KEYBOARD_MAP.ArrowLeft).toBe('moveLeft');
    expect(KEYBOARD_MAP.KeyD).toBe('moveRight');
    expect(KEYBOARD_MAP.KeyS).toBe('moveDown');
  });

  it('maps the footy actions', () => {
    expect(KEYBOARD_MAP.Space).toBe('kick');
    expect(KEYBOARD_MAP.KeyE).toBe('handball');
    expect(KEYBOARD_MAP.KeyF).toBe('tackle');
    expect(KEYBOARD_MAP.KeyQ).toBe('switchPlayer');
    expect(KEYBOARD_MAP.Tab).toBe('switchPlayer');
    expect(KEYBOARD_MAP.ShiftLeft).toBe('sprint');
    expect(KEYBOARD_MAP.KeyB).toBe('bounce');
    expect(KEYBOARD_MAP.Escape).toBe('pause');
  });
});

describe('gamepad (controller) mapping — standard gamepad layout', () => {
  it('maps face buttons to the four core actions', () => {
    expect(GAMEPAD_BUTTONS[0]).toBe('kick');       // A / Cross
    expect(GAMEPAD_BUTTONS[1]).toBe('handball');   // B / Circle
    expect(GAMEPAD_BUTTONS[2]).toBe('tackle');     // X / Square
    expect(GAMEPAD_BUTTONS[3]).toBe('switchPlayer'); // Y / Triangle
  });

  it('maps triggers, bumpers and the menu buttons', () => {
    expect(GAMEPAD_BUTTONS[5]).toBe('sprint'); // RB / R1
    expect(GAMEPAD_BUTTONS[7]).toBe('sprint'); // RT / R2
    expect(GAMEPAD_BUTTONS[4]).toBe('bounce'); // LB / L1
    expect(GAMEPAD_BUTTONS[9]).toBe('pause');  // Start
    expect(GAMEPAD_BUTTONS[8]).toBe('back');   // Back/Select
  });

  it('maps the d-pad', () => {
    expect(GAMEPAD_BUTTONS[12]).toBe('moveUp');
    expect(GAMEPAD_BUTTONS[13]).toBe('moveDown');
    expect(GAMEPAD_BUTTONS[14]).toBe('moveLeft');
    expect(GAMEPAD_BUTTONS[15]).toBe('moveRight');
  });

  it('applies a radial dead zone to the sticks', () => {
    expect(applyDeadZone(0.1, 0.1)).toEqual({ x: 0, y: 0 });
    expect(applyDeadZone(0, 0)).toEqual({ x: 0, y: 0 });
    const full = applyDeadZone(1, 0);
    expect(full.x).toBeCloseTo(1, 5);
    const mid = applyDeadZone(0.6, 0);
    expect(mid.x).toBeGreaterThan(0);
    expect(mid.x).toBeLessThan(1);
    // direction is preserved
    const diag = applyDeadZone(0.8, 0.8);
    expect(Math.abs(diag.x - diag.y)).toBeLessThan(1e-9);
  });

  it('dead zone magnitude is configurable and sane', () => {
    expect(GAMEPAD_DEADZONE).toBeGreaterThan(0.05);
    expect(GAMEPAD_DEADZONE).toBeLessThan(0.5);
  });
});

describe('touch controls', () => {
  it('virtual stick delta is clamped to the stick radius', () => {
    const small = touchStickDelta(0.17, 0.73, 0.16, 0.72, 0.16);
    expect(Math.hypot(small.x, small.y)).toBeLessThanOrEqual(1.001);
    const big = touchStickDelta(0.5, 0.72, 0.16, 0.72, 0.16);
    expect(Math.hypot(big.x, big.y)).toBeCloseTo(1, 5);
    expect(big.x).toBeCloseTo(1, 5);
  });

  it('touch buttons resolve to the nearest button', () => {
    const kick = TOUCH_BUTTONS.kick;
    expect(touchButtonAt(kick.x, kick.y)).toBe('kick');
    const handball = TOUCH_BUTTONS.handball;
    expect(touchButtonAt(handball.x, handball.y)).toBe('handball');
    expect(touchButtonAt(0.05, 0.05)).toBeNull();
  });

  it('touch layout exposes all five actions with big targets', () => {
    for (const key of ['kick', 'handball', 'tackle', 'sprint', 'switchPlayer'] as const) {
      const b = TOUCH_BUTTONS[key];
      expect(b.r).toBeGreaterThanOrEqual(0.05);
    }
  });
});

describe('edge detection', () => {
  it('reports an action only on the transition to pressed', () => {
    const e = new EdgeDetector();
    expect(e.update(new Set(['kick']))).toEqual(new Set(['kick']));
    expect(e.update(new Set(['kick']))).toEqual(new Set());
    expect(e.update(new Set())).toEqual(new Set());
    expect(e.update(new Set(['kick', 'handball']))).toEqual(new Set(['kick', 'handball']));
  });

  it('empty input frames are valid', () => {
    const f = emptyInputFrame();
    expect(f.moveX).toBe(0);
    expect(f.kickReleased).toBe(false);
  });
});
