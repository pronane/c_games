/**
 * Aussie Rules 3D — entry point and game loop.
 *
 * Fixed-timestep simulation (the laws engine + physics run at 60 Hz),
 * variable-rate rendering, broadcast camera, synthesized audio, HUD and
 * menus — playable with keyboard, gamepad or touch on any device.
 */
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MatchSim, HumanIntent, emptyHumanIntent } from './sim/match';
import { RulesEngine } from './rules/engine';
import { AFL_SETTINGS, MatchEvent, MatchSettings, scoreString } from './rules/types';
import { BroadcastCamera } from './render/camera';
import { createWorld, drawScoreboard, World } from './render/scene';
import {
  createPlayerViews,
  syncPlayerViews,
  triggerOneShot,
  PlayerView,
  Teams,
} from './render/players';
import { InputManager } from './input/input';
import { InputFrame } from './input/mappings';
import { MatchAudio } from './audio/audio';
import { Hud, Menus, CLUBS, $, createTouchButtons } from './ui/ui';

type GamePhase = 'menu' | 'playing' | 'paused' | 'ended';

const FREE_KICK_TEXT: Record<string, string> = {
  mark: 'MARK!',
  holdingTheBall: 'HOLDING THE BALL!',
  runningTooFar: 'RUNNING TOO FAR!',
  highTackle: 'HIGH TACKLE!',
  pushInTheBack: 'PUSH IN THE BACK!',
  holdingTheMan: 'HOLDING THE MAN!',
  throwing: 'THROWING!',
  trip: 'TRIP!',
  kickInDanger: 'KICK IN DANGER!',
  charge: 'CHARGE!',
  outOnTheFull: 'OUT ON THE FULL!',
  lastDisposalOOB: 'LAST DISPOSAL — FREE KICK',
  deliberateOOB: 'DELIBERATE OUT OF BOUNDS!',
  deliberateRushedBehind: 'DELIBERATE RUSHED BEHIND!',
  interferenceAfterMark: '50m PENALTY!',
  protectedArea: '50m PENALTY!',
  thirdManUp: 'THIRD MAN UP!',
  ruckCrossedCentre: 'RUCK FOUL!',
  kickInNotCleared: 'NOT CLEARED — FREE KICK!',
  advantage: 'PLAY ON!',
};

class Game {
  phase: GamePhase = 'menu';
  world!: World;
  sim: MatchSim | null = null;
  views = new Map<number, PlayerView>();
  ballMesh!: THREE.Group;
  broadcast!: BroadcastCamera;
  input = new InputManager($('game'));
  audio = new MatchAudio();
  hud = new Hud();
  menus = new Menus();
  teams: Teams = {
    home: { ...CLUBS[0] },
    away: { ...CLUBS[1] },
  };
  settings: MatchSettings = {
    ...AFL_SETTINGS,
    quarterSeconds: 300,
    difficulty: 'afl',
    seed: (Math.random() * 1e9) | 0,
  };
  private accum = 0;
  private lastTime = 0;
  private celebrationTimer = 0;
  private scoreboardTimer = 0;
  private menuAngle = 0;
  private touchButtons = new Map<string, HTMLElement>();
  private playerGltf: Awaited<ReturnType<GLTFLoader['loadAsync']>> | null = null;

  async boot(): Promise<void> {
    this.menus.setLoading(0.1, 'Building the Melbourne arena…');
    this.world = await createWorld($('game') as HTMLCanvasElement);
    this.broadcast = new BroadcastCamera(this.world.camera);

    this.menus.setLoading(0.45, 'Rigging the players…');
    const loader = new GLTFLoader();
    this.playerGltf = await loader.loadAsync('./assets/player.glb');
    this.menus.setLoading(0.75, 'Inflating the Sherrin…');
    const ballGltf = await loader.loadAsync('./assets/ball.glb');
    this.ballMesh = ballGltf.scene;
    this.ballMesh.scale.setScalar(1.05);
    this.world.scene.add(this.ballMesh);

    this.menus.setLoading(0.95, 'Ready.');
    this.setupMenus();
    this.setupTouch();
    this.menus.show('title');

    window.addEventListener('resize', () => this.onResize());
    document.addEventListener('visibilitychange', () => {
      if (document.hidden && this.phase === 'playing') this.pause();
    });

    // PWA: allow installing the game on any device
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('./sw.js').catch(() => undefined);
    }

    this.lastTime = performance.now();
    requestAnimationFrame((t) => this.frame(t));
  }

  // ------------------------------------------------------------------ menus

  private setupMenus(): void {
    const selHome = $('sel-home') as HTMLSelectElement;
    const selAway = $('sel-away') as HTMLSelectElement;
    for (let i = 0; i < CLUBS.length; i++) {
      for (const sel of [selHome, selAway]) {
        const opt = document.createElement('option');
        opt.value = String(i);
        opt.textContent = CLUBS[i].name;
        sel.appendChild(opt);
      }
    }
    selHome.value = '0';
    selAway.value = '1';

    $('btn-play').addEventListener('click', () => this.startMatch());
    $('btn-settings').addEventListener('click', () => this.menus.show('settings'));
    $('btn-controls').addEventListener('click', () => this.menus.show('controls'));
    $('btn-settings-back').addEventListener('click', () => this.menus.show('title'));
    $('btn-controls-back').addEventListener('click', () => {
      this.menus.show(this.phase === 'paused' ? 'pause' : 'title');
    });
    $('btn-pause-controls').addEventListener('click', () => this.menus.show('controls'));
    $('btn-resume').addEventListener('click', () => this.resume());
    $('btn-quit').addEventListener('click', () => this.quitToMenu());
    $('btn-rematch').addEventListener('click', () => this.startMatch());
    $('btn-end-menu').addEventListener('click', () => this.quitToMenu());
  }

  private setupTouch(): void {
    const ui = $('touch-ui');
    this.touchButtons = createTouchButtons(ui);
    if (this.input.isTouchDevice) {
      ui.classList.remove('hidden');
    }
  }

  startMatch(): void {
    const hi = Number(( $('sel-home') as HTMLSelectElement).value) || 0;
    const ai = Number(( $('sel-away') as HTMLSelectElement).value) || 1;
    this.teams.home = { ...CLUBS[hi] };
    this.teams.away = { ...CLUBS[ai] };
    this.settings.difficulty = (($('sel-difficulty') as HTMLSelectElement).value as MatchSettings['difficulty']) ?? 'afl';
    this.settings.quarterSeconds = Number(( $('sel-quarters') as HTMLSelectElement).value) || 300;
    this.settings.seed = (Math.random() * 1e9) | 0;
    this.audio.setEnabled(($('chk-sound') as HTMLInputElement).checked);
    this.audio.init();
    this.audio.resume();

    this.sim = new MatchSim(this.settings, this.settings.difficulty, 0);
    this.sim.start();

    // player views
    for (const v of this.views.values()) {
      this.world.scene.remove(v.root);
    }
    this.views = createPlayerViews(this.playerGltf!, this.sim.state, this.teams);
    for (const v of this.views.values()) this.world.scene.add(v.root);

    this.hud.show();
    this.hud.setHint(
      this.input.isTouchDevice
        ? 'Left: stick · Right: KICK / HAND / TACKLE'
        : 'WASD move · Space kick · E handball · F tackle · Shift sprint · Q switch · Esc pause'
    );
    this.menus.hideAll();
    this.phase = 'playing';
    this.accum = 0;
    this.celebrationTimer = 0;
    this.redrawScoreboards();
  }

  pause(): void {
    if (this.phase !== 'playing') return;
    this.phase = 'paused';
    this.menus.show('pause');
  }

  resume(): void {
    if (this.phase !== 'paused') return;
    this.phase = 'playing';
    this.menus.hideAll();
    this.audio.resume();
  }

  quitToMenu(): void {
    this.phase = 'menu';
    this.sim = null;
    for (const v of this.views.values()) this.world.scene.remove(v.root);
    this.views.clear();
    this.hud.hide();
    this.menus.show('title');
  }

  // ------------------------------------------------------------------ loop

  private frame(now: number): void {
    requestAnimationFrame((t) => this.frame(t));
    const dt = Math.min(0.1, (now - this.lastTime) / 1000);
    this.lastTime = now;

    if (this.phase === 'playing' && this.sim) {
      this.stepMatch(dt);
    } else if (this.phase === 'menu') {
      this.menuAngle += dt * 0.06;
      const r = 130;
      this.world.camera.position.set(
        Math.cos(this.menuAngle) * r,
        52,
        Math.sin(this.menuAngle) * r
      );
      this.world.camera.lookAt(0, 4, 0);
      this.world.update(dt, { x: 0, y: 0, z: 0 });
    }

    this.world.renderer.render(this.world.scene, this.world.camera);
    this.audio.settle(dt);
  }

  private stepMatch(dt: number): void {
    const sim = this.sim!;
    const frame = this.input.poll(0);

    if (frame.pause) {
      this.pause();
      return;
    }

    const intent = toHumanIntent(frame);
    const simDt = 1 / 60;
    this.accum = Math.min(this.accum + dt, 0.2);
    let first = true;
    while (this.accum >= simDt) {
      const sub: HumanIntent = {
        ...intent,
        kickReleased: first ? intent.kickReleased : false,
        handball: first ? intent.handball : false,
        switchPlayer: first ? intent.switchPlayer : false,
      };
      const events = sim.update(simDt, sub);
      this.handleEvents(events);
      this.accum -= simDt;
      first = false;
    }

    // celebration camera & one-shot handling
    if (this.celebrationTimer > 0) {
      this.celebrationTimer -= dt;
      if (this.celebrationTimer <= 0) {
        this.broadcast.setMode('broadcast');
      }
    } else if (sim.state.phase === 'freeKick' && sim.state.freeKick?.isSetShot) {
      this.broadcast.setMode('setShot');
    } else if (this.broadcast.mode !== 'celebration') {
      this.broadcast.setMode('broadcast');
    }

    const controlled = sim.controlled();
    syncPlayerViews(this.views, sim.state, dt, this.celebrationTimer > 0);

    // ball mesh
    const b = sim.state.ball;
    this.ballMesh.position.set(b.x, b.y, b.z);
    if (b.mode === 'loose') {
      this.ballMesh.rotation.x += b.vy * dt * 1.2;
      this.ballMesh.rotation.z += b.vx * dt * 0.8;
    }

    this.broadcast.update(
      dt,
      sim.state,
      controlled?.x ?? 0,
      controlled?.z ?? 0
    );
    this.world.update(dt, b);

    // HUD
    this.hud.update(dt, sim.state, this.teams.home.name, this.teams.away.name);
    if (controlled) {
      this.hud.setPlayer(controlled.number, controlled.name);
    }
    this.hud.setCharge(sim.kickCharge);
    this.hud.drawRadar(sim.state, sim.controlledId);

    // touch button visuals
    if (this.input.isTouchDevice) {
      for (const [key, el] of this.touchButtons) {
        const active =
          (key === 'kick' && frame.kickHeld) ||
          (key === 'handball' && frame.handball) ||
          (key === 'tackle' && frame.tackle) ||
          (key === 'sprint' && frame.sprint) ||
          (key === 'switchPlayer' && frame.switchPlayer);
        el.classList.toggle('active', active);
      }
    }

    this.scoreboardTimer -= dt;
    if (this.scoreboardTimer <= 0) {
      this.redrawScoreboards();
      this.scoreboardTimer = 4;
    }
  }

  private handleEvents(events: MatchEvent[]): void {
    const sim = this.sim!;
    for (const e of events) {
      switch (e.type) {
        case 'goal': {
          const team = e.team === 0 ? this.teams.home.name : this.teams.away.name;
          this.hud.callout('GOAL!!', `${team} · ${scoreString(sim.state.scores[e.team!])}`, '#ffd23f');
          this.audio.goalHorn();
          this.audio.cheer(1);
          this.celebrationTimer = 3.6;
          this.broadcast.setMode('celebration');
          this.input.rumble(0, 0.8, 0.5, 320);
          this.redrawScoreboards();
          break;
        }
        case 'behind': {
          this.hud.callout('BEHIND', '', '#cfe3ff');
          this.audio.whistle(false);
          this.audio.cheer(0.25);
          this.redrawScoreboards();
          break;
        }
        case 'mark': {
          this.hud.callout('MARK!', '', '#ffffff');
          this.audio.cheer(0.3);
          const view = e.playerId !== undefined ? this.views.get(e.playerId) : undefined;
          if (view) triggerOneShot(view, 'mark_jump');
          break;
        }
        case 'freeKick': {
          const text = FREE_KICK_TEXT[e.text ?? ''] ?? 'FREE KICK';
          this.hud.callout(text, e.team === 0 ? this.teams.home.name : this.teams.away.name);
          this.audio.whistle(false);
          break;
        }
        case 'fiftyMetres': {
          this.hud.callout('50m PENALTY!', '', '#ff9d2e');
          this.audio.whistle(true);
          break;
        }
        case 'tackle': {
          this.audio.kick(0.4);
          const view = e.playerId !== undefined ? this.views.get(e.playerId) : undefined;
          if (view) triggerOneShot(view, 'tackle');
          if (e.playerId === sim.controlledId || sim.state.ball.holderId === sim.controlledId) {
            this.input.rumble(0, 0.55, 0.35, 160);
          }
          break;
        }
        case 'stat': {
          // disposals: one-shot kick / handball animations + sound
          if (e.text === 'kick' || e.text === 'handball') {
            const view = e.playerId !== undefined ? this.views.get(e.playerId) : undefined;
            if (view) triggerOneShot(view, e.text === 'kick' ? 'kick' : 'handball');
            if (e.playerId === sim.controlledId) this.audio.kick(e.text === 'kick' ? 1 : 0.55);
            else if (Math.random() < 0.3) this.audio.kick(0.4);
          } else if (e.text === 'bounce') {
            this.audio.bounce();
          }
          break;
        }
        case 'ballUp':
        case 'throwIn':
        case 'centreBallUp':
          this.audio.whistle(false);
          break;
        case 'kickIn':
          this.hud.callout('KICK-IN', '', '#cfe3ff');
          break;
        case 'lastDisposal':
        case 'outOnTheFull':
          this.hud.callout(
            e.type === 'outOnTheFull' ? 'OUT ON THE FULL' : 'LAST DISPOSAL',
            e.team === 0 ? this.teams.home.name : this.teams.away.name
          );
          this.audio.whistle(false);
          break;
        case 'quarterEnd': {
          const q = sim.state.clock.quarter;
          const label = q === 1 ? 'QUARTER TIME' : q === 2 ? 'HALF TIME' : q === 3 ? 'THREE-QUARTER TIME' : 'FULL TIME';
          this.hud.callout(label, '', '#ffd23f');
          this.audio.siren(false);
          break;
        }
        case 'matchEnd': {
          this.audio.siren(true);
          this.phase = 'ended';
          setTimeout(() => {
            this.menus.showEnd(sim.state, this.teams.home.name, this.teams.away.name);
          }, 1600);
          break;
        }
        case 'siren':
          break;
        default:
          break;
      }
    }
  }

  private redrawScoreboards(): void {
    if (!this.sim) return;
    const s = this.sim.state;
    for (const screen of this.world.screens) {
      drawScoreboard(
        screen,
        this.teams.home.name,
        this.teams.away.name,
        scoreString(s.scores[0]),
        scoreString(s.scores[1]),
        s.clock.quarter,
        `${Math.floor(s.clock.secondsRemaining / 60)}:${String(Math.floor(s.clock.secondsRemaining % 60)).padStart(2, '0')}`
      );
    }
  }

  private onResize(): void {
    const w = window.innerWidth;
    const h = window.innerHeight;
    this.world.camera.aspect = w / h;
    this.world.camera.updateProjectionMatrix();
    this.world.renderer.setSize(w, h);
  }
}

function toHumanIntent(f: InputFrame): HumanIntent {
  const intent = emptyHumanIntent();
  intent.moveX = f.moveX;
  intent.moveZ = f.moveZ;
  intent.sprint = f.sprint;
  intent.kickHeld = f.kickHeld;
  intent.kickReleased = f.kickReleased;
  intent.handball = f.handball;
  intent.tackle = f.tackle;
  intent.switchPlayer = f.switchPlayer;
  intent.bounce = f.bounce;
  intent.aimZ = f.aimZ;
  return intent;
}

// Kick off
const game = new Game();
game.boot().catch((err) => {
  console.error(err);
  const load = document.getElementById('loadtext');
  if (load) load.textContent = `Failed to start: ${String(err)}`;
});

// expose for debugging / verification scripts
(window as unknown as { __ard: { game: Game; RulesEngine: typeof RulesEngine } }).__ard = {
  game,
  RulesEngine,
};
