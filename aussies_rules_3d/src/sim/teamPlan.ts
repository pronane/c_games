import { predictDrop } from './ball';
import { clampInside, defendGoalX } from '../rules/field';
import type { MatchState } from '../rules/types';
export interface TeamJob { kind: 'contest' | 'short' | 'outlet' | 'mark' | 'stage' | 'shape'; x: number; z: number }
/** Persistent assignments: no re-ranking every player tick and no RNG consumption. */
export class TeamPlan {
  private remaining = 0;
  private holder: number | null = null;
  private phase = '';
  private roster = '';
  readonly diagnostics = { replans: 0, roleChanges: 0 };
  jobs = new Map<number, TeamJob>();
  update(state: MatchState, dt: number): Map<number, TeamJob> {
    this.remaining -= dt;
    const roster = state.players.filter(p => !p.onBench).map(p => p.id).join(',');
    if (this.remaining > 0 && this.holder === state.ball.holderId && this.phase === state.phase && this.roster === roster) return this.jobs;
    this.phase = state.phase; this.roster = roster;
    this.diagnostics.replans++;
    const previous = this.jobs;
    this.remaining = 0.8;
    this.holder = state.ball.holderId;
    this.jobs = new Map();
    const b = state.ball;
    const landing = b.mode === 'loose' && b.y > 2 ? predictDrop(b) : b;
    const anchor = clampInside(landing.x, landing.z, 4);
    const carrier = state.players.find(p => p.id === b.holderId && b.mode === 'held');
    for (const team of [0, 1] as const) {
      const players = state.players.filter(p => !p.onBench && p.team === team && p.id !== carrier?.id)
        .sort((a, c) => Math.hypot(a.x - anchor.x, a.z - anchor.z) - Math.hypot(c.x - anchor.x, c.z - anchor.z) || a.id - c.id);
      for (const p of players) this.jobs.set(p.id, { kind: 'shape', x: p.x, z: p.z });
      // Restarts retain role homes, not inherited contest/receiving pressure.
      if (state.phase !== 'live') {
        // Around-ground restarts need nearby participants, not everyone at home.
        // These are reserved positions, not chase/tackle permissions.
        if (state.phase === 'ballUp' || state.phase === 'throwIn') {
          const length = Math.hypot(anchor.x, anchor.z) || 1;
          const ix = length > 1 ? -anchor.x / length : 1, iz = length > 1 ? -anchor.z / length : 0;
          const side = team === 0 ? 1 : -1;
          players.slice(0, 2).forEach((p, rank) => {
            const lateral = side * (rank === 0 ? 2.5 : 4);
            const spot = clampInside(anchor.x + ix * (4 + rank * 5) - iz * lateral,
              anchor.z + iz * (4 + rank * 5) + ix * lateral, 3);
            this.jobs.set(p.id, { kind: 'stage', x: spot.x, z: spot.z });
          });
        }
        continue;
      }
      const attack = carrier?.team === team;
      const count = attack ? 0 : 2;
      players.slice(0, count).forEach(p => this.jobs.set(p.id, { kind: 'contest', x: anchor.x, z: anchor.z }));
      const dir = team === 0 ? 1 : -1;
      // Only the possessing team (or loose-ball team) reserves receiving lanes.
      if (!carrier || attack) players.slice(count, count + 2).forEach((p, rank) => {
        const side = anchor.z > 0 ? -1 : 1;
        this.jobs.set(p.id, { kind: rank === 0 ? 'short' : 'outlet',
          x: anchor.x + dir * (rank === 0 ? 4 : 16),
          z: anchor.z + side * (rank === 0 ? 10 : -16) });
      });
      if (carrier && !attack) {
        const goalX = defendGoalX(team);
        const available = state.players.filter(p => !p.onBench && p.team !== team && p.id !== carrier.id && Math.abs(p.x - goalX) < 55);
        const taken = new Set<number>();
        for (const defender of players.filter(p => ['fullback', 'keyDefender', 'halfBack'].includes(p.role) && this.jobs.get(p.id)?.kind === 'shape')) {
          const target = available.filter(p => !taken.has(p.id)).sort((a, b) =>
            Math.hypot(a.x - defender.x, a.z - defender.z) - Math.hypot(b.x - defender.x, b.z - defender.z) || a.id - b.id)[0];
          if (!target) continue;
          taken.add(target.id);
          const gx = goalX - target.x, gz = -target.z, length = Math.hypot(gx, gz) || 1;
          this.jobs.set(defender.id, { kind: 'mark', x: target.x + gx / length * 2, z: target.z + gz / length * 2 });
        }
      }
    }
    for (const [id, job] of this.jobs) if (previous.get(id)?.kind !== job.kind) this.diagnostics.roleChanges++;
    return this.jobs;
  }
}
