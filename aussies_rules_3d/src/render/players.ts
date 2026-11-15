/**
 * Players — the rigged, skinned, animated footballers from Gaelic_Football_3d
 * (`assets/gaelic_player.glb`, Sprite Forge squad, 3 appearance variants),
 * trimmed to the outfield body meshes, cloned per player with AFL club kit
 * colours and squad numbers, driven by an animation state machine.
 */
import * as THREE from 'three';
import { GLTF } from 'three/addons/loaders/GLTFLoader.js';
import { clone as skeletonClone } from 'three/addons/utils/SkeletonUtils.js';
import { MatchState, PlayerState, TeamId } from '../rules/types';

export interface PlayerView {
  root: THREE.Group;
  mixer: THREE.AnimationMixer;
  actions: Map<string, THREE.AnimationAction>;
  current: string;
  playerId: number;
  team: TeamId;
  number: number;
  facing: number;
  /** Coloured ground ring (yellow + pulsing for the controlled player). */
  ring: THREE.Mesh<THREE.RingGeometry, THREE.MeshBasicMaterial>;
  /** Pass-assist ring: cyan = handpass target, orange = kick target, hidden otherwise. */
  targetRing: THREE.Mesh<THREE.RingGeometry, THREE.MeshBasicMaterial>;
  /** White ring that shrinks and fades for ~0.7 s after control switches. */
  flashRing: THREE.Mesh<THREE.RingGeometry, THREE.MeshBasicMaterial>;
  /** Always-on overhead marker for the controlled player — visible in a scrum. */
  chevron: THREE.Mesh<THREE.ConeGeometry, THREE.MeshBasicMaterial>;
}

export interface Teams {
  home: { primary: string; secondary: string; name: string };
  away: { primary: string; secondary: string; name: string };
}

export type PlayerAnim =
  | 'idle' | 'walk' | 'run' | 'sprint' | 'run_ball' | 'kick' | 'handball'
  | 'tackle' | 'mark_jump' | 'celebrate' | 'hit_deck';

/** Appearance variants kept in the trimmed GLB (v0 short-hair, v2 beard, v6 afro). */
const VARIANT_PREFIXES = ['v0_', 'v2_', 'v6_'];

/** Game-facing anim name → Gaelic_Football_3d clip. */
const CLIP_ALIASES: Record<string, string> = {
  idle: 'idle',
  walk: 'jog',
  run: 'run',
  sprint: 'run',
  run_ball: 'run_ball',
  kick: 'kick_run',
  handball: 'hand_pass',
  tackle: 'tackle_reach',
  mark_jump: 'catch',
  celebrate: 'celebrate_jump',
  hit_deck: 'knocked_down',
};

/** Per-anim default playback rate (sprint plays the run clip faster). */
const ANIM_TIMESCALE: Record<string, number> = {
  sprint: 1.18,
  walk: 0.9,
};

function luminance(hex: string): number {
  const n = parseInt(hex.replace('#', ''), 16);
  const r = (n >> 16) & 0xff, g = (n >> 8) & 0xff, b = n & 0xff;
  return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
}

function numberTexture(number: number, primary: string): THREE.CanvasTexture {
  const c = document.createElement('canvas');
  c.width = 128;
  c.height = 128;
  const g = c.getContext('2d')!;
  g.fillStyle = primary;
  g.fillRect(0, 0, 128, 128);
  const ink = luminance(primary) > 0.6 ? '#101010' : '#f5f5f5';
  g.fillStyle = ink;
  g.font = 'bold 92px system-ui, sans-serif';
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.fillText(String(number), 64, 68);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function tintKits(root: THREE.Object3D, team: TeamId, teams: Teams, number: number): void {
  const kit = team === 0 ? teams.home : teams.away;
  root.traverse((obj) => {
    if (!(obj instanceof THREE.Mesh)) return;
    const wasSingle = !Array.isArray(obj.material);
    const mats = (Array.isArray(obj.material) ? obj.material : [obj.material]) as THREE.MeshStandardMaterial[];
    const meshName = (obj.name ?? '').toLowerCase();
    const cloned = mats.map((m) => {
      const mat = m.clone();
      // The Gaelic GLB ships one shared 'kit' material; AFL club colours are
      // flat tints per kit piece, identified by the vN_* mesh names.
      if (meshName.endsWith('jersey')) {
        mat.map = numberTexture(number, kit.primary);
        mat.color = new THREE.Color(0xffffff);
      } else if (meshName.endsWith('shorts') || meshName.endsWith('socks')) {
        mat.color = new THREE.Color(kit.secondary);
      } else if (meshName.endsWith('boots')) {
        mat.color = new THREE.Color(0x151515);
      }
      mat.roughness = 0.82;
      mat.metalness = 0.02;
      return mat;
    });
    // Keep the original shape: three.js only iterates geometry.groups when the
    // material is an array, and these geometries have no groups — an array
    // here would render NOTHING at all.
    obj.material = wasSingle ? cloned[0] : cloned;
    obj.castShadow = true;
    obj.receiveShadow = false;
    if (obj instanceof THREE.SkinnedMesh) {
      obj.frustumCulled = false;
    }
  });
}

export function createPlayerViews(
  gltf: GLTF,
  state: MatchState,
  teams: Teams
): Map<number, PlayerView> {
  const views = new Map<number, PlayerView>();
  const clips = new Map<string, THREE.AnimationClip>();
  for (const clip of gltf.animations) clips.set(clip.name, clip);

  // Pre-build one pruned template per appearance variant so per-player clones
  // don't carry the other variants' meshes around.
  const templates = VARIANT_PREFIXES.map((prefix) => {
    const t = skeletonClone(gltf.scene) as THREE.Group;
    const drop: THREE.Object3D[] = [];
    t.traverse((o) => {
      const m = /^v\d+_/.exec(o.name ?? '');
      if (m && !o.name.startsWith(prefix)) drop.push(o);
    });
    for (const o of drop) o.removeFromParent();
    return t;
  });

  for (const p of state.players) {
    const template = templates[p.id % templates.length];
    const root = skeletonClone(template) as THREE.Group;
    tintKits(root, p.team, teams, p.number);
    root.scale.setScalar(1.0);
    root.position.set(p.x, 0, p.z);
    root.rotation.y = -p.facing + Math.PI / 2;

    const mixer = new THREE.AnimationMixer(root);
    const actions = new Map<string, THREE.AnimationAction>();
    for (const [gameName, clipName] of Object.entries(CLIP_ALIASES)) {
      const clip = clips.get(clipName);
      if (!clip) continue;
      const action = mixer.clipAction(clip);
      if (gameName === 'kick' || gameName === 'handball' || gameName === 'tackle' || gameName === 'mark_jump' || gameName === 'hit_deck') {
        action.setLoop(THREE.LoopOnce, 1);
        action.clampWhenFinished = true;
      }
      actions.set(gameName, action);
    }
    const idle = actions.get('idle');
    idle?.play();

    // ground ring: light-blue (home) / pink (away), yellow + pulse when controlled
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(1.18, 1.46, 28),
      new THREE.MeshBasicMaterial({
        color: p.team === 0 ? 0x7fd0ff : 0xff8f8f,
        transparent: true,
        opacity: 0.65,
        side: THREE.DoubleSide,
        depthWrite: false,
      })
    );
    ring.rotation.x = -Math.PI / 2;
    ring.position.y = 0.03;
    ring.renderOrder = 2;
    root.add(ring);

    const targetRing = new THREE.Mesh(
      new THREE.RingGeometry(1.52, 1.8, 28),
      new THREE.MeshBasicMaterial({
        color: 0x35e0ff,
        transparent: true,
        opacity: 0.9,
        side: THREE.DoubleSide,
        depthWrite: false,
      })
    );
    targetRing.rotation.x = -Math.PI / 2;
    targetRing.position.y = 0.038;
    targetRing.renderOrder = 3;
    targetRing.visible = false;
    root.add(targetRing);

    const flashRing = new THREE.Mesh(
      new THREE.RingGeometry(1.12, 1.86, 28),
      new THREE.MeshBasicMaterial({
        color: 0xffffff,
        transparent: true,
        opacity: 0,
        side: THREE.DoubleSide,
        depthWrite: false,
      })
    );
    flashRing.rotation.x = -Math.PI / 2;
    flashRing.position.y = 0.045;
    flashRing.renderOrder = 4;
    flashRing.visible = false;
    root.add(flashRing);

    const chevron = new THREE.Mesh(
      new THREE.ConeGeometry(0.34, 0.66, 4),
      new THREE.MeshBasicMaterial({
        color: 0xffd23f,
        transparent: true,
        opacity: 0.95,
        depthTest: false,
      })
    );
    chevron.rotation.x = Math.PI; // apex down
    chevron.position.y = 2.42;
    chevron.renderOrder = 10;
    chevron.visible = false;
    root.add(chevron);

    views.set(p.id, {
      root,
      mixer,
      actions,
      current: 'idle',
      playerId: p.id,
      team: p.team,
      number: p.number,
      facing: p.facing,
      ring,
      targetRing,
      flashRing,
      chevron,
    });
  }
  return views;
}

/** Smoothly switch the playing clip (with a cross-fade). */
export function playAnim(view: PlayerView, anim: PlayerAnim, fade = 0.18): void {
  if (view.current === anim) return;
  const next = view.actions.get(anim);
  const prev = view.actions.get(view.current);
  if (!next) return;
  next.enabled = true;
  next.reset();
  next.setEffectiveTimeScale(ANIM_TIMESCALE[anim] ?? 1);
  next.setEffectiveWeight(1);
  next.play();
  if (prev && prev !== next) prev.crossFadeTo(next, fade, false);
  view.current = anim;
}

/** Decide which clip a player should be showing right now. */
export function chooseAnim(
  p: PlayerState,
  view: PlayerView,
  ball: { mode: string; holderId: number | null },
  isControlled: boolean,
  celebrating: boolean
): PlayerAnim {
  if (celebrating && ball.holderId === p.id) return 'celebrate';
  const speed = Math.hypot(p.vx, p.vz);
  if (ball.holderId === p.id) {
    if (speed > 5.4) return 'run_ball';
    if (speed > 1.2) return 'run_ball';
    return 'idle';
  }
  void view;
  void isControlled;
  if (speed > 6.2) return 'sprint';
  if (speed > 3.2) return 'run';
  if (speed > 0.8) return 'walk';
  return 'idle';
}

export const SWITCH_FLASH_TIME = 0.7;

export interface TargetRings {
  /** Which assist ring to show on the human carrier's option (or none). */
  mode: 'none' | 'hand' | 'kick';
  handId: number;
  kickId: number;
}

export interface SwitchFlash {
  id: number;
  /** Seconds REMAINING of the flash (counts down from SWITCH_FLASH_TIME). */
  remaining: number;
}

export function syncPlayerViews(
  views: Map<number, PlayerView>,
  state: MatchState,
  dt: number,
  celebrating: boolean,
  controlledId: number | null = null,
  markersOn = true,
  targets: TargetRings = { mode: 'none', handId: -1, kickId: -1 },
  flash: SwitchFlash = { id: -1, remaining: 0 }
): void {
  const now = performance.now() / 1000;
  for (const p of state.players) {
    const view = views.get(p.id);
    if (!view) continue;
    if (p.onBench) {
      view.root.visible = false;
      continue;
    }
    view.root.visible = true;

    // team rings — the quickest way to read who is who from the broadcast cam
    if (!markersOn) {
      view.ring.visible = false;
    } else {
      view.ring.visible = true;
      if (p.id === controlledId) {
        view.ring.material.color.setHex(0xffd23f);
        view.ring.material.opacity = 0.95;
        view.ring.scale.setScalar(1 + 0.16 * Math.sin(now * 5));
      } else {
        view.ring.material.color.setHex(view.team === 0 ? 0x7fd0ff : 0xff8f8f);
        view.ring.material.opacity = 0.6;
        view.ring.scale.setScalar(1);
      }
    }

    // pass-assist target rings (cyan handpass / orange kick)
    {
      const wantId =
        targets.mode === 'hand' ? targets.handId : targets.mode === 'kick' ? targets.kickId : -1;
      if (wantId === p.id) {
        view.targetRing.visible = true;
        view.targetRing.material.color.setHex(targets.mode === 'hand' ? 0x35e0ff : 0xff8c1a);
        view.targetRing.material.opacity = 0.75 + 0.25 * Math.sin(now * 6);
        view.targetRing.scale.setScalar(1 + 0.07 * Math.sin(now * 6));
      } else {
        view.targetRing.visible = false;
      }
    }

    // switch flash — a white ring that shrinks and fades over ~0.7 s
    if (flash.id === p.id && flash.remaining > 0) {
      const age = SWITCH_FLASH_TIME - flash.remaining;
      const k = Math.min(1, Math.max(0, age / SWITCH_FLASH_TIME));
      view.flashRing.visible = true;
      view.flashRing.material.opacity = 0.9 * (1 - k);
      view.flashRing.scale.setScalar(2.4 - 1.25 * k);
    } else {
      view.flashRing.visible = false;
    }

    // overhead chevron on YOUR man — readable even inside a scrum
    view.chevron.visible = controlledId !== null && p.id === controlledId;
    if (view.chevron.visible) {
      view.chevron.position.y = 2.42 + 0.09 * Math.sin(now * 4);
      view.chevron.rotation.y = now * 2.2;
    }

    const b = state.ball;
    // ball carrier animates with the ball; others react to movement
    const anim = chooseAnim(p, view, b, false, celebrating);
    if (
      view.current !== 'kick' &&
      view.current !== 'handball' &&
      view.current !== 'tackle' &&
      view.current !== 'mark_jump' &&
      view.current !== 'hit_deck' ||
      view.actions.get(view.current)?.isRunning() === false
    ) {
      playAnim(view, anim);
    }

    view.root.position.set(p.x, p.y, p.z);
    // the model faces -Z in glTF; sim facing is radians where 0 = +x
    view.root.rotation.y = -p.facing - Math.PI / 2;
    view.mixer.update(dt);
  }
}

export function triggerOneShot(view: PlayerView, anim: PlayerAnim): void {
  playAnim(view, anim, 0.08);
}
