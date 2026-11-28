import { MotionProbe } from './render/motionProbe';
import { BallReadability } from './render/ballReadability';
import { captureIntent } from './sim/captureScenario';
/**
 * Aussie Rules 3D — entry point and game loop.
 *
 * Fixed-timestep simulation (the laws engine + physics run at 60 Hz),
 * variable-rate rendering, broadcast camera, synthesized audio, HUD and
 * menus — playable with keyboard, gamepad or touch on any device.
 */
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { loadMotionAssets, type MotionAssets } from './render/motionBinding';
import { MatchSim, HumanIntent, emptyHumanIntent } from './sim/match';
import type { PlayerState } from './rules/types';
import { RulesEngine } from './rules/engine';
import { AFL_SETTINGS, FIELD, MatchEvent, MatchSettings, scoreString } from './rules/types';
import { BroadcastCamera } from './render/camera';
import { createWorld, drawScoreboard, updateLedScorebug, World } from './render/scene';
import {
  createPlayerViews,
  syncPlayerViews,
  triggerOneShot,
  PlayerView,
  Teams,
  SWITCH_FLASH_TIME,
} from './render/players';
import { InputManager } from './input/input';
import { InputFrame } from './input/mappings';
import { MatchAudio } from './audio/audio';
import { LOD_DISTANCES, pickLodQuality, type LodQuality } from './render/lod';

/**
 * A/B capture mode for the CI visual workflow (?ab=1, optional ?lod=ultra|high|performance):
 * fixed attract seed so two runs are frame-comparable, hides menu overlays so frames
 * show unobstructed attract play, and logs AB_STATS renderer counters to the console
 * every couple of seconds (captured by the CI console log). No effect otherwise.
 */
const AB_PARAMS = typeof window !== 'undefined' ? new URLSearchParams(window.location.search) : null;
const AB_MODE = !!AB_PARAMS?.has('ab');
const AB_LOD = AB_PARAMS?.get('lod');
const AB_MATCH = AB_MODE && AB_PARAMS?.get('scenario') === 'match';
const AB_MANUAL = AB_MATCH && AB_PARAMS?.get('drive') === 'manual';
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
  private ballReadability!: BallReadability;
  private captureTick = 0;
  private motionProbe = new MotionProbe();
  ballShadow!: THREE.Mesh<THREE.CircleGeometry, THREE.MeshBasicMaterial>;
  broadcast!: BroadcastCamera;
  input = new InputManager($('game'));
  audio = new MatchAudio();
  /** Graphics quality tier — drives the squad LOD switch distances. */
  lodQuality: LodQuality = pickLodQuality(AB_LOD ?? 'high');
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
  private touchButtons = new Map<string, HTMLElement>();
  private playerGltf: Awaited<ReturnType<GLTFLoader['loadAsync']>> | null = null;
  private motionAssets: MotionAssets | null = null;
  private menuFocusIndex = 0;
  private menuFocusedScreen = '';
  private menuNavDir = 0;
  private menuConfirmDown = false;
  private menuBackDown = false;
  private showMarkers = true;
  private hintTimer = 0;
  private fpsEma = 1 / 60;
  private abLastLog = 0;
  private abFrameTimes: number[] = [];
  // camera subject visibility accounting (AB mode — framing regression tripwire)
  private abCamFrames = 0;
  private abCamBallIn = 0;
  private abCamPlayerIn = 0;
  private abCamPlayerFrames = 0;
  private abCamBallMax = 0;
  private abCamPlayerMax = 0;
  private abCamLastLog = 0;
  // attract mode — AI vs AI behind the title menu
  private demoSim: MatchSim | null = null;
  private demoViews = new Map<number, PlayerView>();
  private demoAccum = 0;
  private demoTime = 0;
  private menuCamT = 0;
  // pass-assist target rings + switch flash
  private lastSwitchCount = 0;
  private switchFlashId = -1;
  private switchFlashT = 0;

  async boot(): Promise<void> {
    if (AB_MODE) console.log('AB_BOOT world');
    this.menus.setLoading(0.1, 'Building the Melbourne arena…');
    this.world = await createWorld($('game') as HTMLCanvasElement);
    this.broadcast = new BroadcastCamera(this.world.camera);

    this.menus.setLoading(0.45, 'Rigging the players…');
    const loader = new GLTFLoader();
    try {
      // Built by tools/build_afl_player.py on a networked machine — preferred when present
      this.playerGltf = await loader.loadAsync('./assets/afl_player.glb');
      console.info('AFL player asset loaded (afl_player.glb)');
    } catch {
      this.playerGltf = await loader.loadAsync('./assets/gaelic_player.glb');
      console.info('afl_player.glb not built yet — using gaelic_player.glb');
    }
    if (AB_MODE) console.log('AB_BOOT player loaded');
    this.motionAssets = await loadMotionAssets();
    if (AB_MODE) console.log(`AB_BOOT motion=${!!this.motionAssets}`);
    this.menus.setLoading(0.75, 'Inflating the Sherrin…');
    const ballGltf = await loader.loadAsync('./assets/ball.glb');
    this.ballMesh = ballGltf.scene;
    // AFL Sherrin is ~27 cm long — the raw GLB is modelled ~1.45 m, scale it down.
    this.ballMesh.scale.setScalar(0.19);
    this.world.scene.add(this.ballMesh);
    this.ballReadability = new BallReadability(this.world.scene, this.ballMesh);
    // soft blob under the ball — reads at broadcast distance, survives flight
    const cnv = document.createElement('canvas');
    cnv.width = 64;
    cnv.height = 64;
    const g2d = cnv.getContext('2d')!;
    const grad = g2d.createRadialGradient(32, 32, 2, 32, 32, 32);
    grad.addColorStop(0, 'rgba(0,0,0,0.6)');
    grad.addColorStop(0.7, 'rgba(0,0,0,0.25)');
    grad.addColorStop(1, 'rgba(0,0,0,0)');
    g2d.fillStyle = grad;
    g2d.fillRect(0, 0, 64, 64);
    const ballShadowTex = new THREE.CanvasTexture(cnv);
    this.ballShadow = new THREE.Mesh(
      new THREE.CircleGeometry(0.42, 16),
      new THREE.MeshBasicMaterial({ map: ballShadowTex, transparent: true, depthWrite: false })
    );
    this.ballShadow.rotation.x = -Math.PI / 2;
    this.ballShadow.position.y = 0.022;
    this.ballShadow.renderOrder = 1;
    this.world.scene.add(this.ballShadow);

    if (AB_MODE) console.log('AB_BOOT assets loaded');
    this.menus.setLoading(0.95, 'Ready.');
    this.setupMenus();
    this.setupTouch();
    this.startAttract();
    this.menus.show('title');
    if (AB_MATCH) this.startMatch();
    if (AB_MODE) {
      // capture the unobstructed attract demo (deterministic — see AB_PARAMS)
      document.querySelectorAll('.screen').forEach((el) => el.classList.add('hidden'));
    }

    // mouse-wheel zoom on the broadcast cam (auto-recentres after 3 s)
    ($('game') as HTMLCanvasElement).addEventListener(
      'wheel',
      (e: WheelEvent) => {
        e.preventDefault();
        this.broadcast.addZoom(e.deltaY > 0 ? 0.11 : -0.11);
      },
      { passive: false }
    );

    window.addEventListener('resize', () => this.onResize());
    document.addEventListener('visibilitychange', () => {
      if (document.hidden && this.phase === 'playing') this.pause();
    });

    // PWA: allow installing the game on any device
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('./sw.js').catch(() => undefined);
    }

    // Live gamepad status in the Controls screen
    const refreshPadStatus = () => this.updateGamepadStatus();
    window.addEventListener('gamepadconnected', refreshPadStatus);
    window.addEventListener('gamepaddisconnected', refreshPadStatus);
    window.setInterval(refreshPadStatus, 1500);
    refreshPadStatus();

    if (AB_MANUAL) {
      // CI owns simulation progress, not SwiftShader's wall-clock frame rate.
      Object.assign(window, { __advanceCapture: (ticks: number) => {
        for (let i = 0; i < Math.min(600, Math.max(0, ticks)); i++) this.stepMatch(1 / 60);
        this.ballReadability.update(this.ballMesh, this.world.camera, this.world.renderer.domElement.clientHeight, true);
        this.world.renderer.render(this.world.scene, this.world.camera);
        const cp = this.sim?.controlled();
        const b = this.sim!.state.ball;
        const crowd5 = this.sim!.state.players.filter(p => !p.onBench && Math.hypot(p.x - b.x, p.z - b.z) < 5).length;
        const ballNdc = new THREE.Vector3(b.x, b.y, b.z).project(this.world.camera);
        const groundNdc = new THREE.Vector3(b.x, 0.15, b.z).project(this.world.camera);
        const state = { view: this.broadcast.view,
          cameraOutsideBroadcastSide: this.broadcast.mode !== 'broadcast' || this.broadcast.view !== 'broadcast' || this.world.camera.position.z >= FIELD.boundaryB + 8,
          groundNdc: [groundNdc.x, groundNdc.y, groundNdc.z],
          worldBall: [b.x, b.y, b.z], ballNdc: [ballNdc.x, ballNdc.y, ballNdc.z],
          cameraPosition: this.world.camera.position.toArray(),
          motion: this.motionProbe.snapshot(), team: this.sim!.teamDiagnostics,
          motionLoaded: cp ? !!this.views.get(cp.id)?.motion : false,
          clip: cp ? this.views.get(cp.id)?.motion?.state.currentClipId ?? null : null,
          modelYaw: cp ? this.views.get(cp.id)?.root.rotation.y : null,
          mode: this.broadcast.mode, tick: this.captureTick, seed: this.settings.seed, phase: this.sim!.state.phase,
          ballMinorPixels: this.ballReadability.minorPixels,
          heading: cp?.facing, velocity: cp ? [cp.vx, cp.vz] : null, crowd5,
          camera: { ...this.broadcast.diagnostics }, sim: this.sim!.diagnostics };
        console.log(`CAPTURE_STATE ${JSON.stringify(state)}`);
        return state;
      } });
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
    // graphics quality applies live — next sync picks up the new distances
    ($('sel-graphics') as HTMLSelectElement).addEventListener('change', (e) => {
      this.lodQuality = pickLodQuality((e.target as HTMLSelectElement).value);
    });
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
    for (const v of this.demoViews.values()) this.world.scene.remove(v.root);
    this.demoViews.clear();
    this.demoSim = null;
    const hi = Number(( $('sel-home') as HTMLSelectElement).value) || 0;
    const ai = Number(( $('sel-away') as HTMLSelectElement).value) || 1;
    this.teams.home = { ...CLUBS[hi] };
    this.teams.away = { ...CLUBS[ai] };
    this.settings.difficulty = (($('sel-difficulty') as HTMLSelectElement).value as MatchSettings['difficulty']) ?? 'afl';
    this.settings.quarterSeconds = Number(( $('sel-quarters') as HTMLSelectElement).value) || 300;
    this.settings.seed = AB_MODE ? 0x5eed5eed : (Math.random() * 1e9) | 0;
    this.lodQuality = pickLodQuality(($('sel-graphics') as HTMLSelectElement | null)?.value);
    this.audio.setEnabled(($('chk-sound') as HTMLInputElement).checked);
    this.audio.init();
    this.audio.resume();

    this.sim = new MatchSim(this.settings, this.settings.difficulty, 0);
    this.sim.start();

    // player views
    for (const v of this.views.values()) {
      this.world.scene.remove(v.root);
    }
    this.views = createPlayerViews(this.playerGltf!, this.sim.state, this.teams, this.motionAssets);
    for (const v of this.views.values()) this.world.scene.add(v.root);

    this.hud.show();
    this.hud.setHint(
      this.input.isTouchDevice
        ? 'Left: stick · Right: KICK / HAND / TACKLE'
        : 'WASD move · Space kick · E handpass (target ring) · F tackle · Q switch · C camera · wheel zoom · V markers · Esc pause'
    );
    this.menus.hideAll();
    this.phase = 'playing';
    this.accum = 0;
    this.captureTick = 0;
    this.motionProbe = new MotionProbe();
    this.celebrationTimer = 0;
    this.redrawScoreboards();
  }

  // -------------------------------------------------------- attract mode

  private startAttract(): void {
    for (const v of this.demoViews.values()) this.world.scene.remove(v.root);
    this.demoViews.clear();
    const seed = AB_MODE ? 0x5eed5eed : (Math.random() * 1e9) | 0;
    const sim = new MatchSim(
      { ...AFL_SETTINGS, quarterSeconds: 300, difficulty: 'afl', seed },
      'afl',
      0
    );
    sim.attract = true;
    sim.start();
    this.demoSim = sim;
    this.demoAccum = 0;
    this.demoTime = 0;
    this.menuCamT = 0;
    this.demoViews = createPlayerViews(
      this.playerGltf!, sim.state,
      { home: { ...CLUBS[0] }, away: { ...CLUBS[1] } },
      this.motionAssets
    );
    for (const v of this.demoViews.values()) this.world.scene.add(v.root);
  }

  /** Run the AI-vs-AI match behind the menu and sweep broadcast cameras over it. */
  private stepAttract(dt: number): void {
    const sim = this.demoSim;
    if (!sim) return;
    const empty = emptyHumanIntent();
    const simDt = 1 / 60;
    this.demoAccum = Math.min(this.demoAccum + dt, 0.2);
    while (this.demoAccum >= simDt) {
      sim.update(simDt, empty);
      this.demoAccum -= simDt;
    }
    this.demoTime += dt;
    if (sim.state.phase === 'matchEnd' || this.demoTime > 110) {
      this.startAttract();
      return;
    }
    // cinematic sweep: broadcast → aerial → wing, 9 s each
    this.menuCamT += dt;
    const CYCLE: Array<'broadcast' | 'aerial' | 'wing'> = ['broadcast', 'aerial', 'wing'];
    this.broadcast.view = CYCLE[Math.floor(this.menuCamT / 9) % CYCLE.length];
    const b = sim.state.ball;
    syncPlayerViews(this.demoViews, sim.state, dt, false, -1, true, undefined, undefined, this.world.camera, LOD_DISTANCES[this.lodQuality]);
    this.ballMesh.position.set(b.x, b.y, b.z);
    this.ballShadow.position.set(b.x, 0.022, b.z);
    const air = Math.max(0, b.y - 0.11);
    this.ballShadow.material.opacity = Math.max(0.06, 0.5 - air * 0.045);
    this.ballShadow.scale.setScalar(1 + air * 0.08);
    this.broadcast.update(dt, sim.state, null);
    this.world.update(dt, b);
    this.scoreboardTimer -= dt;
    if (this.scoreboardTimer <= 0) {
      this.drawBoardsFor(sim, this.teamsForDemo());
      this.scoreboardTimer = 4;
    }
  }

  private teamsForDemo(): Teams {
    return { home: { ...CLUBS[0] }, away: { ...CLUBS[1] } };
  }

  /** Scoreboards with an explicit match — used by the attract demo. */
  private drawBoardsFor(sim: MatchSim, teams: Teams): void {
    const s = sim.state;
    for (const screen of this.world.screens) {
      drawScoreboard(
        screen,
        teams.home.name,
        teams.away.name,
        scoreString(s.scores[0]),
        scoreString(s.scores[1]),
        s.clock.quarter,
        `${Math.floor(s.clock.secondsRemaining / 60)}:${String(Math.floor(s.clock.secondsRemaining % 60)).padStart(2, '0')}`
      );
    }
    updateLedScorebug(
      this.world.led,
      teams.home.name,
      teams.away.name,
      scoreString(s.scores[0]),
      scoreString(s.scores[1]),
      s.clock.quarter,
      `Q${s.clock.quarter} ${Math.floor(s.clock.secondsRemaining / 60)}:${String(Math.floor(s.clock.secondsRemaining % 60)).padStart(2, '0')}`
    );
  }

  /** White ring that shrinks around whichever player control just moved to. */
  private updateSwitchFlash(sim: MatchSim, dt: number): void {
    if (sim.switchCount !== this.lastSwitchCount) {
      this.lastSwitchCount = sim.switchCount;
      this.switchFlashT = SWITCH_FLASH_TIME;
      this.switchFlashId = sim.controlledId;
    }
    if (this.switchFlashT > 0) this.switchFlashT = Math.max(0, this.switchFlashT - dt);
  }

  /** Edge arrow that points at your player when he leaves the frame. */
  private updateOffscreenArrow(p: PlayerState | null): void {
    const el = document.getElementById('offscreen');
    if (!el) return;
    if (!p) {
      el.classList.add('hidden');
      return;
    }
    const cam = this.world.camera;
    const v = new THREE.Vector3(p.x, 1.6, p.z);
    v.project(cam);
    const W = window.innerWidth;
    const H = window.innerHeight;
    const behind = v.z > 1;
    const margin = 60;
    const sx = behind ? -v.x : v.x;
    const sy = behind ? v.y : -v.y;
    const len = Math.hypot(sx, sy) || 1;
    const dx = sx / len;
    const dy = sy / len;
    const onScreen =
      !behind &&
      ((v.x * 0.5 + 0.5) * W) >= margin &&
      ((v.x * 0.5 + 0.5) * W) <= W - margin &&
      ((-v.y * 0.5 + 0.5) * H) >= margin &&
      ((-v.y * 0.5 + 0.5) * H) <= H - margin;
    if (onScreen) {
      el.classList.add('hidden');
      return;
    }
    const tx = dx >= 0.001 ? (W - margin - W / 2) / dx : dx <= -0.001 ? (margin - W / 2) / dx : Infinity;
    const ty = dy >= 0.001 ? (H - margin - H / 2) / dy : dy <= -0.001 ? (margin - H / 2) / dy : Infinity;
    const t = Math.min(tx, ty);
    el.style.left = `${W / 2 + dx * t}px`;
    el.style.top = `${H / 2 + dy * t}px`;
    const arrow = document.getElementById('offscreenArrow');
    if (arrow) arrow.style.transform = `rotate(${Math.atan2(dy, dx) + Math.PI / 2}rad)`;
    const num = document.getElementById('offscreenNum');
    if (num) num.textContent = `#${p.number}`;
    el.classList.remove('hidden');
  }

  // ------------------------------------------------------- gamepad in menus

  /** A line in the Controls screen showing whether a pad is seen (Windows often needs one button press first). */
  private updateGamepadStatus(): void {
    const el = document.getElementById('gamepad-status');
    if (!el) return;
    const pads = this.input.connectedPads();
    if (pads.length > 0) {
      el.textContent = `● Controller detected: ${pads[0].id}`;
      el.classList.add('ok');
    } else {
      el.textContent = 'No controller detected — press any button on your gamepad, then re-open this screen';
      el.classList.remove('ok');
    }
  }

  private menuButtons(screen: HTMLElement): HTMLButtonElement[] {
    return Array.from(screen.querySelectorAll('button')).filter((b) => !b.disabled);
  }

  /** Activate the focused menu button, or A=select / B=back / Start=resume semantics for gamepads. */
  private updateMenuInput(frame: InputFrame): void {
    const cur = this.menus.current;
    if (cur === 'loading') return;
    const screen = document.getElementById(`screen-${cur}`);
    if (!screen || screen.classList.contains('hidden')) return;

    if (this.menuFocusedScreen !== cur) {
      this.menuFocusedScreen = cur;
      this.menuNavDir = 0;
      // drop focus rings left behind on previously-shown screens
      document.querySelectorAll('.screen button.focused').forEach((el) => el.classList.remove('focused'));
      const buttons = this.menuButtons(screen);
      const primary = buttons.findIndex((b) => b.classList.contains('primary'));
      this.menuFocusIndex = primary >= 0 ? primary : 0;
    }

    const buttons = this.menuButtons(screen);
    if (buttons.length === 0) return;
    this.menuFocusIndex = Math.min(this.menuFocusIndex, buttons.length - 1);

    // vertical navigation (arrows / W,S / d-pad / left stick), edge-triggered
    const nav = Math.abs(frame.moveZ) > 0.5 ? Math.sign(frame.moveZ) : 0;
    if (nav !== 0 && this.menuNavDir === 0) {
      this.menuFocusIndex = (this.menuFocusIndex + nav + buttons.length) % buttons.length;
    }
    this.menuNavDir = nav;

    for (let i = 0; i < buttons.length; i++) {
      buttons[i].classList.toggle('focused', i === this.menuFocusIndex);
    }

    // A / Cross is the 'kick' action and B / Circle is 'handball' — inside a
    // menu they mean select / back instead. Both rising edges (plus Enter and
    // Back/Select) activate accordingly.
    const confirmNow = frame.confirm || frame.kickHeld;
    const confirmEdge = confirmNow && !this.menuConfirmDown;
    this.menuConfirmDown = confirmNow;
    const backNow = frame.back || frame.handball;
    const backEdge = backNow && !this.menuBackDown;
    this.menuBackDown = backNow;

    if (confirmEdge) {
      buttons[this.menuFocusIndex]?.click();
      return;
    }
    if (frame.pause && cur === 'pause') {
      this.resume();
      return;
    }
    if (backEdge) {
      const back =
        cur === 'settings' ? 'btn-settings-back'
        : cur === 'controls' ? 'btn-controls-back'
        : cur === 'pause' ? 'btn-quit'
        : cur === 'end' ? 'btn-end-menu'
        : null;
      if (back) document.getElementById(back)?.click();
    }
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
    this.startAttract();
    this.menus.show('title');
  }

  // ------------------------------------------------------------------ loop

  private frame(now: number): void {
    requestAnimationFrame((t) => this.frame(t));
    const wallDt = Math.max(1e-4, (now - this.lastTime) / 1000);
    const dt = AB_MATCH ? 1 / 30 : Math.min(0.1, wallDt);
    this.lastTime = now;

    if (this.phase === 'playing' && this.sim) {
      if (!AB_MANUAL) this.stepMatch(dt);
    } else {
      // menu-like phase: controller/keyboard navigation for the visible screen
      this.updateMenuInput(this.input.poll(0));
    }
    if (this.phase === 'menu') {
      this.stepAttract(dt);
    }

    this.ballReadability.update(this.ballMesh, this.world.camera,
      this.world.renderer.domElement.clientHeight, this.phase === 'playing' || this.phase === 'menu');
    this.world.renderer.render(this.world.scene, this.world.camera);
    if (AB_MODE) Object.assign(window, { __captureReady: true });
    if (AB_MODE) {
      this.fpsEma += ((1 / wallDt) - this.fpsEma) * 0.05;
      this.abFrameTimes.push(wallDt);
      if (this.abFrameTimes.length > 240) this.abFrameTimes.shift();
      // camera visibility: is the ball / your man inside the safe NDC box?
      {
        const camSim = this.sim ?? this.demoSim;
        const camBall = camSim?.state.ball ?? null;
        if (camBall && this.broadcast.mode !== 'celebration') {
          const cam = this.world.camera;
          const ndcOf = (x: number, y: number, z: number) => {
            const v = new THREE.Vector3(x, y, z).project(cam);
            return Number.isFinite(v.x) && Number.isFinite(v.y) && v.z >= -1 && v.z <= 1 ? v : null;
          };
          this.abCamFrames++;
          const bn = ndcOf(camBall.x, Math.max(camBall.y, 0.15), camBall.z);
          if (bn && Math.abs(bn.x) <= 0.78 && Math.abs(bn.y) <= 0.78) this.abCamBallIn++;
          if (bn) this.abCamBallMax = Math.max(this.abCamBallMax, Math.abs(bn.x), Math.abs(bn.y));
          if (this.phase === 'playing' && this.sim) {
            const cp = this.sim.controlled();
            if (cp) {
              const pn = ndcOf(cp.x, 1.0 + (cp.y ?? 0), cp.z);
              this.abCamPlayerFrames++;
              if (pn && Math.abs(pn.x) <= 0.78 && Math.abs(pn.y) <= 0.78) this.abCamPlayerIn++;
              if (pn) this.abCamPlayerMax = Math.max(this.abCamPlayerMax, Math.abs(pn.x), Math.abs(pn.y));
            }
          }
        }
        if (now - this.abCamLastLog > 2000 && this.abCamFrames > 0) {
          const pct = (n: number, d: number) => ((100 * n) / Math.max(1, d)).toFixed(1);
          console.log(
            `AB_CAMSTAT frames=${this.abCamFrames} ball_in=${pct(this.abCamBallIn, this.abCamFrames)} ` +
              `player_in=${this.abCamPlayerFrames > 0 ? pct(this.abCamPlayerIn, this.abCamPlayerFrames) : 'na'} ` +
              `ball_max_ndc=${this.abCamBallMax.toFixed(2)} ` +
              `player_max_ndc=${this.abCamPlayerFrames > 0 ? this.abCamPlayerMax.toFixed(2) : 'na'}`
          );
          this.abCamFrames = 0;
          this.abCamBallIn = 0;
          this.abCamPlayerIn = 0;
          this.abCamPlayerFrames = 0;
          this.abCamBallMax = 0;
          this.abCamPlayerMax = 0;
          this.abCamLastLog = now;
          console.log(`AB_PLAY ${JSON.stringify({ tick: this.captureTick,
            ballMinorPixels: +this.ballReadability.minorPixels.toFixed(2),
            camera: this.broadcast.diagnostics, sim: this.sim?.diagnostics ?? null })}`);
        }
      }
      if (now - this.abLastLog > 2000 && this.abFrameTimes.length >= 20) {
        const info = this.world.renderer.info;
        const sorted = [...this.abFrameTimes].sort((a, b) => a - b);
        const pct = (q: number) => sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))] * 1000;
        console.log(
          `AB_STATS fps=${this.fpsEma.toFixed(1)} p50_ms=${pct(0.5).toFixed(1)} p95_ms=${pct(0.95).toFixed(1)} tris=${info.render.triangles} calls=${info.render.calls} textures=${info.memory.textures} geometries=${info.memory.geometries} lod=${this.lodQuality}`
        );
        this.abFrameTimes.length = 0;
        this.abLastLog = now;
      }
    }
    this.audio.settle(dt);
  }

  private stepMatch(dt: number): void {
    const sim = this.sim!;
    const frame = this.input.poll(0);

    if (frame.pause) {
      this.pause();
      return;
    }
    if (frame.camera) {
      this.hud.callout(`CAMERA: ${this.broadcast.cycleView()}`, '', '#cfe3ff');
    }
    if (frame.toggleMarkers) {
      this.showMarkers = !this.showMarkers;
      this.hud.callout(this.showMarkers ? 'PLAYER MARKERS: ON' : 'PLAYER MARKERS: OFF', '', '#cfe3ff');
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
      const events = sim.update(simDt, AB_MATCH ? captureIntent(this.captureTick++) : sub);
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

    this.updateSwitchFlash(sim, dt);
    const controlled = sim.controlled();
    const carrierIsHuman =
      sim.state.ball.mode === 'held' && sim.state.ball.holderId === sim.controlledId;
    const targetMode: 'none' | 'hand' | 'kick' = carrierIsHuman
      ? frame.kickHeld
        ? 'kick'
        : 'hand'
      : 'none';
    syncPlayerViews(
      this.views, sim.state, dt, this.celebrationTimer > 0, sim.controlledId, this.showMarkers,
      { mode: targetMode, handId: sim.handTargetId, kickId: sim.kickTargetId },
      { id: this.switchFlashT > 0 ? this.switchFlashId : -1, remaining: this.switchFlashT },
      this.world.camera,
      LOD_DISTANCES[this.lodQuality]
    );
    if (AB_MATCH && controlled) {
      const view = this.views.get(controlled.id);
      if (view) {
        view.root.updateMatrixWorld(true);
        const forward = new THREE.Vector3(0, 0, -1).applyQuaternion(view.root.getWorldQuaternion(new THREE.Quaternion()));
        const feet = ['foot_l', 'foot_r'].map((name, i) => {
          const bone = view.root.getObjectByName(name);
          if (!bone) return null;
          const p = bone.getWorldPosition(new THREE.Vector3());
          const contact = i === 0 ? view.motion?.footPlantedLeft : view.motion?.footPlantedRight;
          return { x: p.x, y: p.y, z: p.z, contact: !!contact };
        });
        this.motionProbe.observe(controlled.id, { x: controlled.vx, z: controlled.vz }, forward,
          feet.filter((f): f is NonNullable<typeof f> => f !== null), dt);
      }
    }
    this.updateOffscreenArrow(controlled);

    // ball mesh
    const b = sim.state.ball;
    this.ballMesh.position.set(b.x, b.y, b.z);
    this.ballShadow.position.set(b.x, 0.022, b.z);
    const air = Math.max(0, b.y - 0.11);
    this.ballShadow.material.opacity = Math.max(0.06, 0.5 - air * 0.045);
    this.ballShadow.scale.setScalar(1 + air * 0.08);
    if (b.mode === 'loose') {
      this.ballMesh.rotation.x += b.vy * dt * 1.2;
      this.ballMesh.rotation.z += b.vx * dt * 0.8;
    }

    this.broadcast.update(
      dt,
      sim.state,
      controlled ? { x: controlled.x, y: 1.0 + (controlled.y ?? 0), z: controlled.z } : null
    );
    this.world.update(dt, b);

    // HUD
    this.hintTimer -= dt;
    if (this.hintTimer <= 0) {
      this.hintTimer = 0.6;
      if (!this.input.isTouchDevice) this.hud.setHint(this.contextHint());
    }
    this.hud.update(dt, sim.state, this.teams.home.name, this.teams.away.name);
    if (controlled) {
      this.hud.setPlayer(controlled.number, controlled.name, controlled.role);
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

  private playWhistle(long: boolean): void {
    if (this.sim) this.sim.diagnostics.whistles++;
    this.audio.whistle(long);
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
          this.playWhistle(false);
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
          this.playWhistle(false);
          break;
        }
        case 'fiftyMetres': {
          this.hud.callout('50m PENALTY!', '', '#ff9d2e');
          this.playWhistle(true);
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
          this.playWhistle(false);
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
          this.playWhistle(false);
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
    this.drawBoardsFor(this.sim, this.teams);
  }

  /** A one-line, always-relevant coaching hint for what's happening right now. */
  private contextHint(): string {
    const sim = this.sim!;
    const b = sim.state.ball;
    const phase = sim.state.phase;
    const hasBall = b.mode === 'held' && b.holderId === sim.controlledId;

    if (phase === 'freeKick' && sim.state.freeKick?.isSetShot) {
      return 'SET SHOT — hold SPACE to charge, Z / X (or right stick) to bend it, release to kick';
    }
    if (phase === 'freeKick') {
      return 'FREE KICK — hold SPACE, release to kick · E to handball to a leading teammate';
    }
    if (phase === 'kickIn') {
      return 'KICK-IN — hold SPACE to charge, release to clear it downfield';
    }
    if (phase === 'centreBallUp') {
      return 'BALL-UP — win the tap: F to ruck / contest, Q to switch to support';
    }
    if (hasBall) {
      const num = (id: number) => sim.state.players.find((p) => p.id === id)?.number ?? 0;
      const kickTo = sim.kickTargetId >= 0 ? ` → #${num(sim.kickTargetId)}` : '';
      const handTo = sim.handTargetId >= 0 ? ` → #${num(sim.handTargetId)}` : '';
      return `YOU HAVE IT — SPACE kick${kickTo} (hold for power) · E handball${handTo} · B bounce · Shift sprint`;
    }
    if (b.mode === 'loose') {
      return 'LOOSE BALL — run at it (your best-placed player is auto-selected) · Q to switch · F tackle';
    }
    return 'DEFENDING — F tackle inside ~2 m · Q switch to the goal-side man · C camera';
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
