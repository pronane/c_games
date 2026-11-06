/**
 * Headless match capture — runs the real MatchSim and exports per-frame telemetry
 * (ball + all players + HUD state + events) to JSON for the Blender video tool
 * (tools/blender/gen_match_video.py).
 */
import { writeFileSync } from 'node:fs';
import { MatchSim, emptyHumanIntent, type HumanIntent } from '../../src/sim/match';
import type { MatchSettings, MatchEvent, PlayerState } from '../../src/rules/types';

export interface Frame {
  t: number;
  ball: [number, number, number];
  players: Array<[number, number, number, number, number, number, number]>;
  // [id, x, z, y, facing, speed, animCode]  animCode: 0 idle 1 walk 2 run 3 sprint 4 carrier
  controlledId: number;
  quarter: number;
  clock: number;
  scores: [number, number];
  events: Array<{ type: string; text?: string; team?: number }>;
}

export interface Capture {
  fps: number;
  frames: Frame[];
  goalFrames: number[];
  eventFrames: number[];
  seed: number;
}

function settings(seed: number, quarterSeconds = 300): MatchSettings {
  return { seed, quarterSeconds, quarters: 4, interchange: 5, rotationCap: 75 };
}

/** Simple scripted "you vs the computer" intent: the human team steers toward
 *  goal with the ball carrier; supports, kicks or handballs like a player.
 *  Kicks use the same charge-then-release semantics as the real input layer. */
let charging = 0; // frames the scripted kick button has been held

function scriptedIntent(sim: MatchSim): HumanIntent {
  const it = { ...emptyHumanIntent() };
  const s = sim.state;
  const c = s.players.find((p) => p.id === sim.controlledId);
  if (!c) return it;
  const dirX = c.team === 0 ? 1 : -1;
  const b = s.ball;
  const distGoal = dirX > 0 ? 135 - c.x : c.x + 69;
  const pressured = s.players.some(
    (p) => p.team !== c.team && !p.onBench && Math.hypot(p.x - c.x, p.z - c.z) < 5,
  );
  if (b.holderId === c.id) {
    if (charging > 0) {
      // in the middle of a kick: hold, then release
      charging--;
      if (charging > 0) it.kickHeld = true;
      else it.kickReleased = true;
      it.aimZ = -c.z * 0.02 + (Math.random() - 0.5) * 0.15;
      return it;
    }
    it.moveX = dirX;
    it.moveZ = Math.max(-1, Math.min(1, -c.z * 0.04 + (Math.random() - 0.5) * 0.5));
    if (distGoal < 52 && Math.random() < 0.18) {
      charging = 12 + Math.floor(Math.random() * 8); // ~0.2..0.33s charge
      it.kickHeld = true;
      it.aimZ = -c.z * 0.02 + (Math.random() - 0.5) * 0.15;
    } else if (pressured && Math.random() < 0.22) {
      if (Math.random() < 0.5) it.handball = true;
      else {
        charging = 8 + Math.floor(Math.random() * 6);
        it.kickHeld = true;
        it.aimZ = (Math.random() - 0.5) * 0.6;
      }
    }
  } else {
    charging = 0;
    const dx = b.x - c.x;
    const dz = b.z - c.z;
    const d = Math.hypot(dx, dz) || 1;
    it.moveX = dx / d;
    it.moveZ = dz / d;
    if (b.y > 1.6 && d < 5 && Math.random() < 0.1) it.tackle = true;
    it.sprint = d > 8;
  }
  return it;
}

export function runSearch(
  seeds: number,
  seconds: number,
): { seed: number; score: number; goals: number; ranked: string } {
  const results: Array<{ seed: number; score: number; goals: number }> = [];
  for (let seed = 1; seed <= seeds; seed++) {
    const sim = new MatchSim(settings(seed));
    sim.start();
    let score = 0;
    let goals = 0;
    const steps = Math.floor(seconds * 60);
    for (let i = 0; i < steps; i++) {
      const evs = sim.update(1 / 60, scriptedIntent(sim));
      for (const e of evs) {
        if (e.type === 'goal') {
          score += 60;
          goals++;
        } else if (e.type === 'behind') score += 12;
        else if (e.type === 'mark') score += 6;
        else if (e.type === 'freeKick' || e.type === 'fiftyMetres') score += 3;
        else if (e.type === 'tackle') score += 1.5;
        else if (e.type === 'stat') score += 0.4;
      }
    }
    results.push({ seed, score, goals });
  }
  // rank: goals first, then overall event score
  results.sort((a, b) => b.goals - a.goals || b.score - a.score);
  const top = results[0];
  const ranked = results
    .slice(0, 6)
    .map((r) => `seed ${r.seed}: ${r.goals} goals ${r.score.toFixed(0)}`)
    .join(' | ');
  return { ...top, ranked };
}

export function capture(seed: number, gameSeconds: number, fps: number): Capture {
  const sim = new MatchSim(settings(seed));
  sim.start();
  const out: Capture = { fps, frames: [], goalFrames: [], eventFrames: [], seed };
  const perFrame = 60 / fps; // sim steps per output frame (2.5 at 24 fps)
  const totalFrames = Math.floor(gameSeconds * fps);
  for (let f = 0; f < totalFrames; f++) {
    let toRun = Math.round((f + 1) * perFrame) - Math.round(f * perFrame);
    let events: MatchEvent[] = [];
    while (toRun-- > 0) {
      events = events.concat(sim.update(1 / 60, scriptedIntent(sim)));
    }
    const s = sim.state;
    const c = s.players.find((p) => p.id === sim.controlledId);
    const clock = s.clock;
    const fr: Frame = {
      t: f / fps,
      ball: [r2(s.ball.x), r2(s.ball.y), r2(s.ball.z)],
      players: s.players.map((p: PlayerState) => [
        p.id,
        r2(p.x),
        r2(p.z),
        r2(p.y),
        r2(p.facing),
        r2(p.speed),
        animCode(p, sim),
      ]),
      controlledId: c ? c.id : -1,
      quarter: clock.quarter,
      clock: Math.max(0, clock.secondsRemaining),
      scores: [s.scores[0].goals * 6 + s.scores[0].behinds, s.scores[1].goals * 6 + s.scores[1].behinds],
      events: events.map((e) => ({
        type: e.type,
        text: (e as { text?: string }).text,
        team: e.team,
      })),
    };
    if (events.some((e) => e.type === 'goal')) out.goalFrames.push(f);
    if (events.length) out.eventFrames.push(f);
    out.frames.push(fr);
  }
  return out;
}

function animCode(p: PlayerState, sim: MatchSim): number {
  const b = sim.state.ball;
  if (b.holderId === p.id) return 4;
  if (p.speed > 6.2) return 3;
  if (p.speed > 3.2) return 2;
  if (p.speed > 0.6) return 1;
  return 0;
}

function r2(n: number): number {
  return Math.round(n * 100) / 100;
}
