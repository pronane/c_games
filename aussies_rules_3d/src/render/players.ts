/**
 * Players — the rigged, skinned, animated Aussie rules footballers from
 * Blender (`assets/player.glb`), cloned for both teams with kit colours and
 * squad numbers, driven by an animation state machine.
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
}

export interface Teams {
  home: { primary: string; secondary: string; name: string };
  away: { primary: string; secondary: string; name: string };
}

export type PlayerAnim =
  | 'idle' | 'walk' | 'run' | 'sprint' | 'run_ball' | 'kick' | 'handball'
  | 'tackle' | 'mark_jump' | 'celebrate' | 'hit_deck';

const KIT_MATERIALS = ['jersey', 'shorts', 'socks'];

function numberTexture(number: number, team: TeamId): THREE.CanvasTexture {
  const c = document.createElement('canvas');
  c.width = 128;
  c.height = 128;
  const g = c.getContext('2d')!;
  g.fillStyle = team === 0 ? '#14213d' : '#111111';
  g.fillRect(0, 0, 128, 128);
  g.fillStyle = team === 0 ? '#f5f5f5' : '#f5f5f5';
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
    const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
    obj.material = mats.map((m) => {
      const mat = (m as THREE.MeshStandardMaterial).clone();
      const name = mat.name ?? '';
      if (KIT_MATERIALS.includes(name)) {
        mat.color = new THREE.Color(name === 'jersey' ? kit.primary : kit.secondary);
        if (name === 'jersey') {
          mat.map = numberTexture(number, team);
          mat.color = new THREE.Color(0xffffff);
        }
      }
      mat.roughness = 0.78;
      mat.metalness = 0.02;
      return mat;
    });
    if (obj instanceof THREE.SkinnedMesh) {
      obj.castShadow = true;
      obj.receiveShadow = false;
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

  for (const p of state.players) {
    const root = skeletonClone(gltf.scene) as THREE.Group;
    tintKits(root, p.team, teams, p.number);
    root.scale.setScalar(1.0);
    root.position.set(p.x, 0, p.z);
    root.rotation.y = -p.facing + Math.PI / 2;

    const mixer = new THREE.AnimationMixer(root);
    const actions = new Map<string, THREE.AnimationAction>();
    for (const [name, clip] of clips) {
      const action = mixer.clipAction(clip);
      if (name === 'kick' || name === 'handball' || name === 'tackle' || name === 'mark_jump' || name === 'hit_deck') {
        action.setLoop(THREE.LoopOnce, 1);
        action.clampWhenFinished = true;
      }
      actions.set(name, action);
    }
    const idle = actions.get('idle');
    idle?.play();

    views.set(p.id, {
      root,
      mixer,
      actions,
      current: 'idle',
      playerId: p.id,
      team: p.team,
      number: p.number,
      facing: p.facing,
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
  next.setEffectiveTimeScale(1);
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

export function syncPlayerViews(
  views: Map<number, PlayerView>,
  state: MatchState,
  dt: number,
  celebrating: boolean
): void {
  for (const p of state.players) {
    const view = views.get(p.id);
    if (!view) continue;
    if (p.onBench) {
      view.root.visible = false;
      continue;
    }
    view.root.visible = true;

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
