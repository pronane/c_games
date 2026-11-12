/** HUD, radar, callouts, menus and on-screen touch buttons. */
import { MatchState, TeamId, scoreString, totalPoints } from '../rules/types';
import { formatClock } from '../rules/laws';
import { FIELD } from '../rules/types';
import { TOUCH_BUTTONS } from '../input/mappings';

export interface TeamColors {
  name: string;
  primary: string;
  secondary: string;
}

export const CLUBS: TeamColors[] = [
  { name: 'Melbourne', primary: '#0b2545', secondary: '#e8eef5' },
  { name: 'Collingwood', primary: '#111111', secondary: '#f2f2f2' },
  { name: 'Richmond', primary: '#1a1a1a', secondary: '#ffd23f' },
  { name: 'Carlton', primary: '#12274e', secondary: '#f2f2f2' },
  { name: 'Geelong', primary: '#0b3d66', secondary: '#f2f2f2' },
  { name: 'Hawthorn', primary: '#4d2607', secondary: '#f2c53d' },
  { name: 'Sydney', primary: '#e03a3e', secondary: '#f2f2f2' },
  { name: 'West Coast', primary: '#0b3a73', secondary: '#f2c53d' },
  { name: 'Adelaide', primary: '#c8102e', secondary: '#111111' },
  { name: 'Brisbane', primary: '#7a1524', secondary: '#f2c53d' },
  { name: 'Fremantle', primary: '#2a1a4d', secondary: '#f2f2f2' },
  { name: 'Western Bulldogs', primary: '#12356b', secondary: '#e03a3e' },
];

export function $(id: string): HTMLElement {
  const el = document.getElementById(id);
  if (!el) throw new Error(`missing element #${id}`);
  return el;
}

export class Hud {
  private calloutTimer = 0;
  private subTimer = 0;

  show(): void {
    $('hud').classList.remove('hidden');
  }

  hide(): void {
    $('hud').classList.add('hidden');
  }

  callout(text: string, sub = '', color = '#ffffff'): void {
    const el = $('callout');
    el.textContent = text;
    (el as HTMLElement).style.color = color;
    el.classList.add('show');
    this.calloutTimer = 2.2;
    if (sub) {
      const s = $('subcallout');
      s.textContent = sub;
      s.classList.add('show');
      this.subTimer = 2.6;
    }
  }

  update(dt: number, state: MatchState, homeName: string, awayName: string): void {
    const scores = state.scores;
    $('homeName').textContent = homeName.toUpperCase();
    $('awayName').textContent = awayName.toUpperCase();
    $('homeScore').textContent = scoreString(scores[0]);
    $('awayScore').textContent = scoreString(scores[1]);
    $('quarter').textContent = `Q${state.clock.quarter}`;
    $('clock').textContent = formatClock(state.clock.secondsRemaining);
    $('timeon').textContent = state.clock.timeOn > 1 ? `+${Math.floor(state.clock.timeOn)}s time on` : '';

    if (this.calloutTimer > 0) {
      this.calloutTimer -= dt;
      if (this.calloutTimer <= 0) $('callout').classList.remove('show');
    }
    if (this.subTimer > 0) {
      this.subTimer -= dt;
      if (this.subTimer <= 0) $('subcallout').classList.remove('show');
    }
  }

  setPlayer(number: number, name: string, role?: string): void {
    $('playerNum').textContent = `#${number}`;
    $('playerName').textContent = name;
    const el = document.getElementById('playerRole');
    if (el && role) {
      el.textContent = role.replace(/([a-z])([A-Z])/g, '$1 $2').toUpperCase();
    }
  }

  setCharge(v: number): void {
    ($('chargeFill') as HTMLElement).style.width = `${Math.round(v * 100)}%`;
  }

  setHint(text: string): void {
    $('hint').textContent = text;
  }

  drawRadar(state: MatchState, controlledId: number): void {
    const canvas = $('radar') as HTMLCanvasElement;
    const g = canvas.getContext('2d');
    if (!g) return;
    const W = canvas.width;
    const H = canvas.height;
    g.clearRect(0, 0, W, H);

    // oval boundary
    g.strokeStyle = 'rgba(255,255,255,0.35)';
    g.lineWidth = 2;
    g.beginPath();
    for (let i = 0; i <= 64; i++) {
      const t = (i / 64) * Math.PI * 2;
      const c = Math.cos(t);
      const s = Math.sin(t);
      const x = Math.sign(c) * Math.pow(Math.abs(c), 2 / FIELD.shapeN) * FIELD.boundaryA;
      const z = Math.sign(s) * Math.pow(Math.abs(s), 2 / FIELD.shapeN) * FIELD.boundaryB;
      const px = W / 2 + (x / (FIELD.boundaryA + 4)) * (W / 2 - 6);
      const py = H / 2 + (z / (FIELD.boundaryB + 4)) * (H / 2 - 6);
      if (i === 0) g.moveTo(px, py);
      else g.lineTo(px, py);
    }
    g.closePath();
    g.stroke();

    // goal lines
    g.strokeStyle = 'rgba(255,255,255,0.2)';
    for (const side of [-1, 1]) {
      const gx = W / 2 + ((side * FIELD.goalLineX) / (FIELD.boundaryA + 4)) * (W / 2 - 6);
      g.beginPath();
      g.moveTo(gx, H * 0.28);
      g.lineTo(gx, H * 0.72);
      g.stroke();
    }

    const toPx = (x: number, z: number) => ({
      px: W / 2 + (x / (FIELD.boundaryA + 4)) * (W / 2 - 6),
      py: H / 2 + (z / (FIELD.boundaryB + 4)) * (H / 2 - 6),
    });

    for (const p of state.players) {
      if (p.onBench) continue;
      const { px, py } = toPx(p.x, p.z);
      g.fillStyle = p.team === 0 ? '#7fd0ff' : '#ff8f8f';
      if (p.id === controlledId) {
        g.fillStyle = '#ffd23f';
        g.beginPath();
        g.arc(px, py, 5, 0, Math.PI * 2);
        g.fill();
      } else {
        g.beginPath();
        g.arc(px, py, 3, 0, Math.PI * 2);
        g.fill();
      }
    }

    const ball = toPx(state.ball.x, state.ball.z);
    g.fillStyle = '#ffffff';
    g.beginPath();
    g.arc(ball.px, ball.py, 3.6, 0, Math.PI * 2);
    g.fill();
    g.strokeStyle = '#000';
    g.lineWidth = 1;
    g.stroke();
  }
}

// ------------------------------------------------------------------ menus

export type ScreenName = 'title' | 'settings' | 'controls' | 'pause' | 'end' | 'loading';

export class Menus {
  current: ScreenName = 'loading';

  show(name: ScreenName | 'none'): void {
    for (const id of ['title', 'settings', 'controls', 'pause', 'end', 'loading']) {
      $(`screen-${id}`).classList.add('hidden');
    }
    if (name !== 'none') $(`screen-${name}`).classList.remove('hidden');
    this.current = (name === 'none' ? 'loading' : name) as ScreenName;
  }

  hideAll(): void {
    this.show('none');
  }

  setLoading(progress: number, text: string): void {
    ($('loadfill') as HTMLElement).style.width = `${Math.round(progress * 100)}%`;
    $('loadtext').textContent = text;
  }

  showEnd(state: MatchState, homeName: string, awayName: string): void {
    const [h, a] = state.scores;
    const hp = totalPoints(h);
    const ap = totalPoints(a);
    const title =
      hp === ap ? 'A Draw!' : hp > ap ? `${homeName} Win!` : `${awayName} Win!`;
    $('end-title').textContent = title;
    $('end-score').innerHTML =
      `<div>${homeName.toUpperCase()} &nbsp; <b>${scoreString(h)}</b></div>` +
      `<div>${awayName.toUpperCase()} &nbsp; <b>${scoreString(a)}</b></div>`;
    const marks = state.players.reduce((n, p) => n + (p.distanceRun > 0 ? 0 : 0), 0);
    void marks;
    $('end-stats').innerHTML =
      `Total points: ${hp} — ${ap}<br>` +
      `Quarter length: ${state.settings.quarterSeconds / 60} min · Difficulty: ${state.settings.difficulty}`;
    this.show('end');
  }
}

// ------------------------------------------------------------ touch buttons

export function createTouchButtons(container: HTMLElement): Map<string, HTMLElement> {
  const els = new Map<string, HTMLElement>();
  for (const [key, b] of Object.entries(TOUCH_BUTTONS)) {
    const el = document.createElement('div');
    el.className = 'touch-btn';
    el.textContent = key === 'switchPlayer' ? 'SWITCH' : key.toUpperCase();
    el.style.left = `${b.x * 100}%`;
    el.style.top = `${b.y * 100}%`;
    el.style.width = `${b.r * 2 * 100}vmin`;
    el.style.height = `${b.r * 2 * 100}vmin`;
    el.style.transform = 'translate(-50%, -50%)';
    container.appendChild(el);
    els.set(key, el);
  }
  return els;
}

export function teamOf(state: MatchState, team: TeamId): { name: string } {
  void state;
  return { name: team === 0 ? 'Home' : 'Away' };
}
