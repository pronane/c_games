import { describe, it, expect } from 'vitest';
import { Vector3 } from 'three';
import { enforceFraming, projectNdc, subjectsInFrame } from '../src/render/framing';

describe('camera framing', () => {
  const pos = new Vector3(0, 0, 10);
  const aim = new Vector3();
  it('projects centre and rejects a point behind camera', () => {
    expect(projectNdc(pos, aim, 46, 16 / 9, aim)).toEqual({ x: 0, y: 0 });
    expect(projectNdc(pos, aim, 46, 16 / 9, new Vector3(0, 0, 20))).toBeNull();
  });
  it('leaves already safe subjects unchanged', () => {
    expect(enforceFraming(pos, aim, 46, 16 / 9, [aim])).toBeNull();
    expect(enforceFraming(pos, aim, 46, 16 / 9, [])).toBeNull();
  });
  it('fits ball and player including perspective depth across aspect ratios', () => {
    for (const aspect of [0.5, 1, 16 / 9, 2.4]) {
      for (let i = 0; i < 200; i++) {
        const subjects = [
          { x: Math.sin(i) * 85, y: i % 40, z: Math.cos(i) * 65, weight: 1.3 },
          { x: Math.cos(i * 3) * 85, y: 1, z: Math.sin(i * 2) * 65 },
        ];
        const p = new Vector3(-30, 30, 96);
        const fix = enforceFraming(p, aim, 46, aspect, subjects);
        expect(subjectsInFrame(fix?.position ?? p, fix?.lookAt ?? aim, 46, aspect, subjects)).toBe(true);
        expect(enforceFraming(p, aim, 46, aspect, subjects)).toEqual(fix);
      }
    }
  });
  it('handles vertical and coincident-centroid camera positions', () => {
    const subjects = [{ x: -60, y: 0, z: 10 }, { x: 60, y: 0, z: -10 }];
    for (const p of [new Vector3(0, 10, 0), new Vector3()]) {
      const fix = enforceFraming(p, aim, 46, 1, subjects)!;
      expect(subjectsInFrame(fix.position, fix.lookAt, 46, 1, subjects)).toBe(true);
    }
  });
});

import { PerspectiveCamera } from 'three';
import { BroadcastCamera, VIEW_ORDER } from '../src/render/camera';
import { MatchSim } from '../src/sim/match';
import { AFL_SETTINGS } from '../src/rules/types';

it('keeps ball and player safe after easing in every gameplay view', () => {
  const sim = new MatchSim({ ...AFL_SETTINGS, seed: 42 });
  sim.start();
  for (const aspect of [0.6, 16 / 9]) {
    const camera = new PerspectiveCamera(46, aspect, 0.5, 1600);
    const broadcast = new BroadcastCamera(camera);
    for (const view of VIEW_ORDER) {
      broadcast.view = view;
      for (const mode of ['broadcast', 'setShot'] as const) {
        broadcast.setMode(mode);
        for (let i = 0; i < 60; i++) {
          const ball = sim.state.ball;
          ball.x = Math.sin(i) * 80;
          ball.z = Math.cos(i) * 60;
          ball.y = i % 35;
          const player = { x: -ball.x, y: 1, z: -ball.z };
          broadcast.update(1 / 60, sim.state, player);
          camera.updateMatrixWorld(true);
          for (const s of [{ ...ball, y: Math.max(ball.y, 0.4) }, player]) {
            const ndc = new Vector3(s.x, s.y, s.z).project(camera);
            expect(Math.abs(ndc.x)).toBeLessThanOrEqual(0.78);
            expect(Math.abs(ndc.y)).toBeLessThanOrEqual(0.78);
            expect(ndc.z).toBeGreaterThanOrEqual(-1);
            expect(ndc.z).toBeLessThanOrEqual(1);
          }
        }
      }
    }
  }
});
