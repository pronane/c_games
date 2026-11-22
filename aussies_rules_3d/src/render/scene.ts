/**
 * The 3D world: renderer, sky, sun, the MCG-scale oval with painted grass
 * markings, the Blender-built stadium, and the animated crowd.
 */
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { FIELD } from '../rules/types';

export interface World {
  renderer: THREE.WebGLRenderer;
  scene: THREE.Scene;
  camera: THREE.PerspectiveCamera;
  sun: THREE.DirectionalLight;
  stadium: THREE.Group;
  screens: { mesh: THREE.Mesh; texture: THREE.CanvasTexture; canvas: HTMLCanvasElement }[];
  led: LedBoards;
  update(dt: number, ball: { x: number; y: number; z: number }): void;
}

export interface LedBoards {
  mesh: THREE.Group;
  canvas: HTMLCanvasElement;
  texture: THREE.CanvasTexture;
  /** Seconds accumulated since the last sponsor rotation. */
  time: number;
  sponsor: number;
  /** Latest scorebug values, so sponsor rotations can redraw the whole ribbon. */
  home: string;
  away: string;
  homeScore: string;
  awayScore: string;
  quarter: number;
  clock: string;
}

export function createRenderer(canvas: HTMLCanvasElement): THREE.WebGLRenderer {
  const renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: true,
    powerPreference: 'high-performance',
  });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.shadowMap.enabled = true;
  // PCFSoftShadowMap was removed in three r187 and silently became PCFShadowMap.
  renderer.shadowMap.type = THREE.PCFShadowMap;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.02;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  return renderer;
}

// --------------------------------------------------------------------- sky

function makeSky(scene: THREE.Scene): void {
  const geo = new THREE.SphereGeometry(900, 32, 18);
  const mat = new THREE.ShaderMaterial({
    side: THREE.BackSide,
    depthWrite: false,
    uniforms: {
      topColor: { value: new THREE.Color(0x2a5aa0) },
      horizonColor: { value: new THREE.Color(0xbcd3e8) },
      bottomColor: { value: new THREE.Color(0xd8e2ea) },
      sunDir: { value: new THREE.Vector3(0.45, 0.55, -0.55).normalize() },
    },
    vertexShader: /* glsl */ `
      varying vec3 vDir;
      void main() {
        vDir = normalize(position);
        gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
      }
    `,
    fragmentShader: /* glsl */ `
      varying vec3 vDir;
      uniform vec3 topColor;
      uniform vec3 horizonColor;
      uniform vec3 bottomColor;
      uniform vec3 sunDir;
      void main() {
        float h = vDir.y;
        vec3 col = mix(horizonColor, topColor, smoothstep(0.0, 0.55, h));
        col = mix(bottomColor, col, smoothstep(-0.15, 0.05, h));
        float sun = pow(max(dot(normalize(vDir), sunDir), 0.0), 220.0);
        float glow = pow(max(dot(normalize(vDir), sunDir), 0.0), 6.0);
        col += vec3(1.0, 0.92, 0.75) * sun * 1.4 + vec3(1.0, 0.85, 0.6) * glow * 0.22;
        gl_FragColor = vec4(col, 1.0);
      }
    `,
  });
  const sky = new THREE.Mesh(geo, mat);
  sky.frustumCulled = false;
  scene.add(sky);
  scene.fog = new THREE.Fog(0xbcd3e8, 320, 880);
}

// -------------------------------------------------------------------- grass

export function makeGrassTexture(): THREE.CanvasTexture {
  const W = 2048;
  const H = 1740;
  const canvas = document.createElement('canvas');
  canvas.width = W;
  canvas.height = H;
  const g = canvas.getContext('2d')!;

  // scale: metres -> px. The texture covers the oval plus apron.
  const metresW = 2 * (FIELD.boundaryA + 6);
  const metresH = 2 * (FIELD.boundaryB + 6);
  const px = W / metresW;
  const py = H / metresH;
  const cx = W / 2;
  const cy = H / 2;
  const mx = (x: number) => cx + x * px;
  const my = (z: number) => cy + z * py;

  // base grass with mow stripes along x
  const stripes = 22;
  for (let i = 0; i < stripes; i++) {
    g.fillStyle = i % 2 === 0 ? '#2e7d32' : '#2a7129';
    g.fillRect((i * W) / stripes, 0, W / stripes + 1, H);
  }
  // subtle noise
  for (let i = 0; i < 4200; i++) {
    const x = Math.random() * W;
    const y = Math.random() * H;
    g.fillStyle = `rgba(${Math.random() > 0.5 ? '255,255,255' : '0,0,0'},0.03)`;
    g.fillRect(x, y, 26, 3);
  }

  // ---- markings (white) ----
  g.strokeStyle = 'rgba(255,255,255,0.92)';
  g.lineWidth = 4.5;

  // boundary (superellipse)
  g.beginPath();
  for (let i = 0; i <= 256; i++) {
    const t = (i / 256) * Math.PI * 2;
    const c = Math.cos(t);
    const s = Math.sin(t);
    const x = Math.sign(c) * Math.pow(Math.abs(c), 2 / FIELD.shapeN) * FIELD.boundaryA;
    const z = Math.sign(s) * Math.pow(Math.abs(s), 2 / FIELD.shapeN) * FIELD.boundaryB;
    if (i === 0) g.moveTo(mx(x), my(z));
    else g.lineTo(mx(x), my(z));
  }
  g.closePath();
  g.stroke();

  // goal lines
  for (const side of [-1, 1]) {
    const gx = side * FIELD.goalLineX;
    g.beginPath();
    g.moveTo(mx(gx), my(-FIELD.behindPostHalf - 2));
    g.lineTo(mx(gx), my(FIELD.behindPostHalf + 2));
    g.stroke();

    // goal square (9 m deep, goal-post wide)
    g.strokeRect(
      mx(side > 0 ? gx : gx - FIELD.goalSquareDepth),
      my(-FIELD.goalPostHalf),
      FIELD.goalSquareDepth * px,
      FIELD.goalPostHalf * 2 * py
    );

    // 50 m arc (bulges from the goal line toward the centre)
    g.beginPath();
    const arcPts = 72;
    for (let i = 0; i <= arcPts; i++) {
      const ang = -Math.PI / 2 + (i / arcPts) * Math.PI;
      const ax = gx - side * FIELD.arcRadius * Math.cos(ang);
      const az = FIELD.arcRadius * Math.sin(ang);
      if (i === 0) g.moveTo(mx(ax), my(az));
      else g.lineTo(mx(ax), my(az));
    }
    g.stroke();
  }

  // centre square & circle
  g.strokeRect(
    mx(-FIELD.centreSquareHalf),
    my(-FIELD.centreSquareHalf),
    FIELD.centreSquareHalf * 2 * px,
    FIELD.centreSquareHalf * 2 * py
  );
  g.beginPath();
  g.arc(mx(0), my(0), FIELD.centreCircleRadius * px, 0, Math.PI * 2);
  g.stroke();

  // mow-stripe highlight for the centre square
  g.fillStyle = 'rgba(255,255,255,0.05)';
  g.fillRect(
    mx(-FIELD.centreSquareHalf),
    my(-FIELD.centreSquareHalf),
    FIELD.centreSquareHalf * 2 * px,
    FIELD.centreSquareHalf * 2 * py
  );

  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return tex;
}

function makeGrass(scene: THREE.Scene): void {
  const tex = makeGrassTexture();
  const size = 2 * (FIELD.boundaryA + 6);
  const geo = new THREE.PlaneGeometry(size, 2 * (FIELD.boundaryB + 6));
  const mat = new THREE.MeshStandardMaterial({
    map: tex,
    roughness: 0.92,
    metalness: 0.0,
  });
  const mesh = new THREE.Mesh(geo, mat);
  mesh.rotation.x = -Math.PI / 2;
  mesh.receiveShadow = true;
  scene.add(mesh);
}

// ------------------------------------------------------------------- crowd

function makeCrowd(scene: THREE.Scene): THREE.InstancedMesh {
  const rows: { x: number; y: number; z: number; ry: number }[] = [];
  const segs = 190;

  const tiers: { start: number; rows: number; depth: number; rise: number; z0: number }[] = [
    { start: 8.5, rows: 13, depth: 1.64, rise: 0.84, z0: 3.2 },
    { start: 34, rows: 11, depth: 1.72, rise: 1.04, z0: 31.0 },
  ];

  for (const tier of tiers) {
    for (let r = 0; r < tier.rows; r++) {
      const off = tier.start + r * tier.depth;
      const y = tier.z0 + r * tier.rise;
      for (let i = 0; i < segs; i++) {
        const t = (i / segs) * Math.PI * 2;
        const c = Math.cos(t);
        const s = Math.sin(t);
        const x = Math.sign(c) * Math.pow(Math.abs(c), 2 / FIELD.shapeN) * (FIELD.boundaryA + 2.2 + off);
        const z = Math.sign(s) * Math.pow(Math.abs(s), 2 / FIELD.shapeN) * (FIELD.boundaryB + 2.2 + off);
        if ((i + r) % 2 === 0 || Math.random() > 0.12) {
          rows.push({ x, y, z, ry: -t + Math.PI / 2 });
        }
      }
    }
  }

  const geo = new THREE.BoxGeometry(0.62, 1.15, 0.55);
  const mat = new THREE.MeshStandardMaterial({ roughness: 0.85, metalness: 0 });
  const inst = new THREE.InstancedMesh(geo, mat, rows.length);
  const dummy = new THREE.Object3D();
  const color = new THREE.Color();
  const palette = [
    0x16233d, 0x2b3a5c, 0x6e2c2c, 0x7a6a4f, 0x30435c, 0x22262e,
    0x8d6e3f, 0x5b2333, 0x24405e, 0x3c4a38, 0x6b6f78, 0x1d2a44,
    0xf2e9dc, 0xc9c2b8,
  ];
  for (let i = 0; i < rows.length; i++) {
    const row = rows[i];
    dummy.position.set(row.x, row.y, row.z);
    dummy.rotation.y = row.ry;
    const h = 0.94 + Math.random() * 0.18;
    dummy.scale.set(1, h, 1);
    dummy.updateMatrix();
    inst.setMatrixAt(i, dummy.matrix);
    color.setHex(palette[Math.floor(Math.random() * palette.length)]);
    inst.setColorAt(i, color);
  }
  inst.instanceMatrix.needsUpdate = true;
  if (inst.instanceColor) inst.instanceColor.needsUpdate = true;
  inst.castShadow = false;
  inst.receiveShadow = false;
  scene.add(inst);
  return inst;
}

// ------------------------------------------------------------------ screens

function makeScreens(stadium: THREE.Group): World['screens'] {
  const screens: World['screens'] = [];
  stadium.traverse((obj) => {
    if (obj instanceof THREE.Mesh && (obj.name === 'Screen.A' || obj.name === 'Screen.B')) {
      const canvas = document.createElement('canvas');
      canvas.width = 1024;
      canvas.height = 360;
      const texture = new THREE.CanvasTexture(canvas);
      texture.colorSpace = THREE.SRGBColorSpace;
      const mat = new THREE.MeshStandardMaterial({
        map: texture,
        emissiveMap: texture,
        emissive: new THREE.Color(0xffffff),
        emissiveIntensity: 1.15,
        roughness: 0.4,
      });
      obj.material = mat;
      screens.push({ mesh: obj, texture, canvas });
    }
  });
  return screens;
}


// -------------------------------------------------------------- led boards

/** Fictional sponsors only — nothing real, nothing trademarked. */
const LED_SPONSORS = [
  'SOUTHERN CROSS TOURS',
  'YARRA POWER',
  'KOOKABURRA SAFE',
  'PUNT & RUN',
  'MELBOURNE MOTORS',
  'BIG W CHICKEN',
  'LAUNCESTON LEADLIGHT',
  'AUSSIE RULES FM',
];
const LED_ROTATE_SECONDS = 3.75;

export function drawLedBoard(boards: LedBoards): void {
  const g = boards.canvas.getContext('2d')!;
  const { width: W, height: H } = boards.canvas;
  // Ribbon background: deep navy with a subtle diagonal sweep so it reads as an
  // LED panel, not a flat sign.
  g.fillStyle = '#060b16';
  g.fillRect(0, 0, W, H);
  const grad = g.createLinearGradient(0, 0, W, H);
  grad.addColorStop(0, 'rgba(46,80,140,0.28)');
  grad.addColorStop(0.5, 'rgba(10,18,34,0)');
  grad.addColorStop(1, 'rgba(46,80,140,0.28)');
  g.fillStyle = grad;
  g.fillRect(0, 0, W, H);

  // Thin amber rails, top and bottom.
  g.fillStyle = '#ffb43a';
  g.fillRect(0, 6, W, 4);
  g.fillRect(0, H - 10, W, 4);

  // Sponsor, left of centre.
  g.fillStyle = '#ffffff';
  g.font = 'bold 58px system-ui, sans-serif';
  g.textAlign = 'left';
  g.textBaseline = 'middle';
  g.fillText(LED_SPONSORS[boards.sponsor % LED_SPONSORS.length], 34, H / 2 + 2);

  // Live scorebug, right of centre.
  const bug = `${boards.home.toUpperCase()} ${boards.homeScore}   ·   ${boards.away.toUpperCase()} ${boards.awayScore}`;
  g.textAlign = 'right';
  g.font = 'bold 46px system-ui, sans-serif';
  g.fillStyle = '#ffd23f';
  g.fillText(bug, W - 34, H / 2 + 2);

  boards.texture.needsUpdate = true;
}

function makeLedBoards(scene: THREE.Scene): LedBoards {
  const SEGS = 72;
  const OFFSET = 4.6;         // metres beyond the boundary superellipse
  const HEIGHT = 1.04;        // board height
  const Y = HEIGHT / 2 + 0.06;

  const canvas = document.createElement('canvas');
  canvas.width = 2048;
  canvas.height = 128;
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;

  const boards: LedBoards = {
    mesh: new THREE.Group(),
    canvas,
    texture,
    time: 0,
    sponsor: 0,
    home: 'HOME',
    away: 'AWAY',
    homeScore: '0.0.0',
    awayScore: '0.0.0',
    quarter: 1,
    clock: '20:00',
  };
  drawLedBoard(boards);

  const mat = new THREE.MeshBasicMaterial({ map: texture, toneMapped: false });
  const group = boards.mesh;
  for (let i = 0; i < SEGS; i++) {
    const t0 = (i / SEGS) * Math.PI * 2;
    const t1 = ((i + 1) / SEGS) * Math.PI * 2;
    const pt = (t: number) => {
      const c = Math.cos(t);
      const s = Math.sin(t);
      return new THREE.Vector3(
        Math.sign(c) * Math.pow(Math.abs(c), 2 / FIELD.shapeN) * (FIELD.boundaryA + OFFSET),
        Y,
        Math.sign(s) * Math.pow(Math.abs(s), 2 / FIELD.shapeN) * (FIELD.boundaryB + OFFSET)
      );
    };
    const a = pt(t0);
    const b = pt(t1);
    const chord = a.distanceTo(b);
    const seg = new THREE.Mesh(new THREE.PlaneGeometry(chord * 1.06, HEIGHT), mat);
    seg.position.copy(a).add(b).multiplyScalar(0.5);
    seg.lookAt(0, Y, 0);
    group.add(seg);
  }
  scene.add(group);
  return boards;
}

// -------------------------------------------------------------------- world

export async function createWorld(canvas: HTMLCanvasElement): Promise<World> {
  const renderer = createRenderer(canvas);
  // Image-based lighting from a generated room environment: gives the PBR
  // materials (skin, boots, kit sheen, screens) something to reflect. The
  // PMREM is generated once at startup — no runtime cost, no HDR asset.
  const pmrem = new THREE.PMREMGenerator(renderer);
  const envMap = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  pmrem.dispose();

  const scene = new THREE.Scene();
  scene.environment = envMap;
  scene.environmentIntensity = 0.45;
  const camera = new THREE.PerspectiveCamera(
    46,
    window.innerWidth / window.innerHeight,
    0.5,
    1600
  );
  camera.position.set(-30, 30, 96);
  camera.lookAt(0, 0, 0);

  makeSky(scene);
  makeGrass(scene);

  // sun + fill
  const sun = new THREE.DirectionalLight(0xfff2dd, 2.6);
  sun.position.set(120, 150, -110);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.camera.near = 10;
  sun.shadow.camera.far = 520;
  const S = 130;
  sun.shadow.camera.left = -S;
  sun.shadow.camera.right = S;
  sun.shadow.camera.top = S;
  sun.shadow.camera.bottom = -S;
  sun.shadow.bias = -0.0006;
  scene.add(sun);
  scene.add(sun.target);

  const hemi = new THREE.HemisphereLight(0xbcd8f2, 0x2e4d2c, 0.85);
  scene.add(hemi);
  const fill = new THREE.DirectionalLight(0xa8c4e8, 0.55);
  fill.position.set(-90, 80, 120);
  scene.add(fill);

  // stadium (Blender-built)
  const loader = new GLTFLoader();
  const gltf = await loader.loadAsync('./assets/stadium.glb');
  const stadium = gltf.scene;
  stadium.traverse((obj) => {
    if (obj instanceof THREE.Mesh) {
      obj.castShadow = false;
      obj.receiveShadow = true;
    }
  });
  scene.add(stadium);

  makeCrowd(scene);
  const screens = makeScreens(stadium);
  const led = makeLedBoards(scene);

  const world: World = {
    renderer,
    scene,
    camera,
    sun,
    stadium,
    screens,
    led,
    update(dt: number, ball: { x: number; y: number; z: number }) {
      // keep the shadow frustum around the action
      sun.target.position.set(ball.x, 0, ball.z);
      sun.position.set(ball.x + 120, 150, ball.z - 110);
      // rotate the LED ribbon sponsor on a fixed cadence
      led.time += dt;
      if (led.time >= LED_ROTATE_SECONDS) {
        led.time = 0;
        led.sponsor = (led.sponsor + 1) % LED_SPONSORS.length;
        drawLedBoard(led);
      }
    },
  };
  return world;
}

/** Refresh the LED ribbon's live scorebug (call wherever the scoreboard redraws). */
export function updateLedScorebug(
  boards: LedBoards,
  home: string,
  away: string,
  homeScore: string,
  awayScore: string,
  quarter: number,
  clock: string
): void {
  boards.home = home;
  boards.away = away;
  boards.homeScore = homeScore;
  boards.awayScore = awayScore;
  boards.quarter = quarter;
  boards.clock = clock;
  drawLedBoard(boards);
}

export function drawScoreboard(
  screen: World['screens'][number],
  home: string,
  away: string,
  homeScore: string,
  awayScore: string,
  quarter: number,
  clock: string
): void {
  const g = screen.canvas.getContext('2d')!;
  const { width: W, height: H } = screen.canvas;
  g.fillStyle = '#06090f';
  g.fillRect(0, 0, W, H);
  g.fillStyle = '#0d1522';
  g.fillRect(8, 8, W - 16, H - 16);

  g.fillStyle = '#ffd23f';
  g.font = 'bold 44px system-ui, sans-serif';
  g.textAlign = 'left';
  g.fillText(home.toUpperCase(), 40, 90);
  g.fillText(away.toUpperCase(), 40, 200);

  g.fillStyle = '#ffffff';
  g.font = 'bold 72px system-ui, sans-serif';
  g.textAlign = 'right';
  g.fillText(homeScore, W - 40, 100);
  g.fillText(awayScore, W - 40, 210);

  g.fillStyle = '#88a4c8';
  g.font = 'bold 38px system-ui, sans-serif';
  g.textAlign = 'center';
  g.fillText(`Q${quarter}   ${clock}`, W / 2, 310);

  screen.texture.needsUpdate = true;
}
