// Pure football rules for the Node Arena FC server. A line-for-line port of arena-fc/Web/MatchRules.gd, so
// the browser's offline game and the online server behave the same way. No state, no I/O.
// Pitch centred on the origin, X is the long axis. Team 0 attacks +X, team 1 attacks -X.
'use strict';

const POST_R = 0.06;
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const smoothstep = (a, b, x) => { const t = clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
const dist2 = (ax, az, bx, bz) => Math.hypot(ax - bx, az - bz);

// Where the keeper should stand. `sign` is +1 for team 0 (own goal on -X). ball = {x,y,z,vx,vy,vz}.
function keeperTarget(ownGoalX, sign, ball, goalW) {
  const toward = -sign * ball.vx > 0;
  const lineX = ownGoalX + sign * 1.2;
  const dx = Math.abs(ball.x - ownGoalX);
  if (toward && Math.abs(ball.vx) > 6 && dx < 30) {
    const t = (lineX - ball.x) / ball.vx;
    if (t > 0) return { x: lineX, z: clamp(ball.z + ball.vz * t, -goalW - 0.6, goalW + 0.6) };
  }
  const z = clamp(ball.z * (0.35 + 0.35 * clamp(1 - dx / 40, 0, 1)), -goalW * 0.85, goalW * 0.85);
  const out = clamp(2 + (30 - Math.min(dx, 30)) * 0.05, 1.2, 3.2);
  return { x: ownGoalX + sign * out, z };
}

function saveChance(miss, speed, reach) {
  if (miss > reach) return 0;
  const closeness = 1 - miss / reach;
  const pace = clamp((speed - 8) / 24, 0, 1);
  return clamp(0.35 + 0.6 * closeness - 0.35 * pace, 0.05, 0.95);
}

function shotError(dist, pressure, power) {
  return clamp(0.015 + dist * 0.0022 + pressure * 0.05 + Math.max(0, power - 0.75) * 0.08, 0.015, 0.22);
}

// 0..1: how closely an opponent marks the carrier. opponents: [{x,z}]
function pressure(carrier, opponents) {
  let best = 1e9;
  for (const o of opponents) best = Math.min(best, dist2(carrier.x, carrier.z, o.x, o.z));
  return clamp(1 - (best - 1) / 5, 0, 1);
}

function distToSegment(p, a, b) {
  const abx = b.x - a.x; const abz = b.z - a.z;
  const l2 = abx * abx + abz * abz;
  if (l2 < 1e-4) return dist2(p.x, p.z, a.x, a.z);
  const t = clamp(((p.x - a.x) * abx + (p.z - a.z) * abz) / l2, 0, 1);
  return dist2(p.x, p.z, a.x + abx * t, a.z + abz * t);
}

function leadPoint(from, cand, candVel, ballSpeed, extra) {
  const t = dist2(from.x, from.z, cand.x, cand.z) / Math.max(ballSpeed, 1);
  return { x: cand.x + candVel.x * (t + extra), z: cand.z + candVel.z * (t + extra) };
}

function passSpeed(dist, through) {
  return clamp(8 + dist * 0.6 + (through ? 3 : 0), 10, 26);
}

function passScore(from, cand, attackSign, opponents, inputDir) {
  const d = dist2(from.x, from.z, cand.x, cand.z);
  if (d < 2) return -1e9;
  const forward = (cand.x - from.x) * attackSign;
  let lane = 9;
  for (const o of opponents) lane = Math.min(lane, distToSegment(o, from, cand));
  let s = forward * 0.22 - d * 0.07 + Math.min(lane, 5) * 1.1;
  if (lane < 1.3) s -= 6;
  if (d > 38) s -= (d - 38) * 0.5;
  if (inputDir && Math.hypot(inputDir.x, inputDir.z) > 0.2) {
    const l = d || 1;
    const il = Math.hypot(inputDir.x, inputDir.z);
    s += (((cand.x - from.x) / l) * (inputDir.x / il) + ((cand.z - from.z) / l) * (inputDir.z / il)) * 6;
  }
  return s;
}

// Ball (radius r) vs posts and crossbar of the goal at x = side * halfL. Returns {hit, vel, pos, kind}.
function woodwork(ball, side, halfL, goalW, goalH, r) {
  const gx = side * halfL;
  const pos = { x: ball.x, y: ball.y, z: ball.z };
  const vel = { x: ball.vx, y: ball.vy, z: ball.vz };
  for (const zs of [-1, 1]) {
    const pz = zs * goalW;
    const dx = pos.x - gx; const dz = pos.z - pz;
    const dist = Math.hypot(dx, dz);
    if (pos.y < goalH && dist < r + POST_R) {
      let nx = -side; let nz = 0;
      if (dist > 1e-4) { nx = dx / dist; nz = dz / dist; }
      const vn = vel.x * nx + vel.z * nz;
      if (vn < 0) {
        return {
          hit: true, kind: 'post',
          vel: { x: vel.x - nx * 1.55 * vn, y: vel.y, z: vel.z - nz * 1.55 * vn },
          pos: { x: gx + nx * (r + POST_R + 0.01), y: pos.y, z: pz + nz * (r + POST_R + 0.01) },
        };
      }
    }
  }
  if (Math.abs(pos.z) < goalW) {
    const dx = pos.x - gx; const dy = pos.y - goalH;
    const dist = Math.hypot(dx, dy);
    if (dist < r + POST_R) {
      let nx = 0; let ny = 1;
      if (dist > 1e-4) { nx = dx / dist; ny = dy / dist; }
      const vn = vel.x * nx + vel.y * ny;
      if (vn < 0) {
        return {
          hit: true, kind: 'bar',
          vel: { x: vel.x - nx * 1.5 * vn, y: vel.y - ny * 1.5 * vn, z: vel.z },
          pos: { x: gx + nx * (r + POST_R + 0.01), y: goalH + ny * (r + POST_R + 0.01), z: pos.z },
        };
      }
    }
  }
  return { hit: false, vel, pos };
}

// Restart for a ball that left the pitch at `pos`, last touched by lastTeam.
function restartFor(pos, lastTeam, halfL, halfW) {
  if (Math.abs(pos.x) <= halfL) {
    return { kind: 'throw', team: 1 - lastTeam, spot: { x: clamp(pos.x, -halfL + 1, halfL - 1), z: halfW * Math.sign(pos.z || 1) } };
  }
  const end = Math.sign(pos.x);
  const defender = end > 0 ? 1 : 0;
  if (lastTeam === defender) {
    const cz = pos.z >= 0 ? 1 : -1;
    return { kind: 'corner', team: 1 - defender, spot: { x: end * (halfL - 0.4), z: halfW * cz * 0.97 } };
  }
  return { kind: 'goal_kick', team: defender, spot: { x: end * (halfL - 5.5), z: 0 } };
}

function foulChance(tacklerVel, victimFacing, sliding) {
  const vl = Math.hypot(tacklerVel.x, tacklerVel.z);
  const fl = Math.hypot(victimFacing.x, victimFacing.z);
  if (vl < 0.5 || fl < 0.1) return 0.08;
  const behind = (tacklerVel.x / vl) * (victimFacing.x / fl) + (tacklerVel.z / vl) * (victimFacing.z / fl);
  return clamp(0.10 + Math.max(0, behind) * 0.4 + (sliding ? 0.15 : 0), 0.05, 0.7);
}

module.exports = {
  clamp, smoothstep, keeperTarget, saveChance, shotError, pressure, distToSegment, leadPoint, passSpeed,
  passScore, woodwork, restartFor, foulChance,
};
