import * as THREE from "three";
import { GLTFLoader } from "../vendor/addons/loaders/GLTFLoader.js";
import { clone as cloneSkeleton } from "../vendor/addons/utils/SkeletonUtils.js";
import { PITCH_L, PITCH_W, CZ, GOAL_W, BAR, ARC } from "./sim.js";

const MODELS = ["broadcast", "follow", "goal", "tactical", "low"];

export async function createWorld(canvas) {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
  renderer.setSize(canvas.clientWidth, canvas.clientHeight, false);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.08;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;

  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x1a120e, 0.0075);
  const camera = new THREE.PerspectiveCamera(38, 16 / 9, 0.15, 420);
  camera.position.set(72, 9, -16);

  buildSky(scene);
  buildPitch(scene);
  buildGoals(scene);
  buildStadium(scene);
  buildLights(scene);

  const gltf = await new GLTFLoader().loadAsync("./models/player.glb");
  const clips = {};
  gltf.animations.forEach((c) => { clips[c.name] = c; });

  const ball = buildBall();
  scene.add(ball.mesh);
  const trail = buildTrail();
  trail.forEach((m) => scene.add(m));

  const views = [];
  const aimRing = new THREE.Mesh(
    new THREE.RingGeometry(0.45, 0.62, 24),
    new THREE.MeshBasicMaterial({ color: 0xffd25a, side: THREE.DoubleSide, transparent: true, opacity: 0.85 })
  );
  aimRing.rotation.x = -Math.PI / 2;
  aimRing.position.y = 0.05;
  scene.add(aimRing);

  const ray = new THREE.Raycaster();
  const ground = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
  const hit = new THREE.Vector3();
  const camPos = new THREE.Vector3(70, 9, -18);
  const camLook = new THREE.Vector3(80, 1, 40);
  let mode = "broadcast";
  let shake = 0;
  let fps = 60;
  let fpsAcc = 0;
  let fpsN = 0;

  function resize() {
    const w = canvas.clientWidth || window.innerWidth;
    const h = canvas.clientHeight || window.innerHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  window.addEventListener("resize", resize);
  resize();

  function spawn(match) {
    views.forEach((v) => { scene.remove(v.root); scene.remove(v.blob); });
    if (views.ref) scene.remove(views.ref.root);
    views.length = 0;
    views.ref = null;
    for (const p of match.players) {
      const view = makePlayer(gltf.scene, clips, p, match.teams[p.team]);
      views.push(view);
      scene.add(view.root);
      scene.add(view.blob);
    }
    const ref = makePlayer(gltf.scene, clips, { number: 0, name: "Ref" }, { jersey: "#141414", shorts: "#141414", socks: "#141414", trim: "#f2f2f2" });
    ref.root.scale.setScalar(1.02);
    views.ref = ref;
    scene.add(ref.root);
  }

  function groundAt(clientX, clientY) {
    const rect = canvas.getBoundingClientRect();
    const ndc = new THREE.Vector2(
      ((clientX - rect.left) / rect.width) * 2 - 1,
      -((clientY - rect.top) / rect.height) * 2 + 1
    );
    ray.setFromCamera(ndc, camera);
    if (ray.ray.intersectPlane(ground, hit)) return { x: hit.x, z: hit.z };
    return null;
  }

  function aimHigh(clientX, clientY, goalX) {
    const bar = worldToScreen(goalX, BAR, CZ);
    if (!bar) return null;
    return clientY < bar.y - 6;
  }

  function worldToScreen(x, y, z) {
    const v = new THREE.Vector3(x, y, z).project(camera);
    if (v.z > 1) return null;
    const rect = canvas.getBoundingClientRect();
    return {
      x: (v.x * 0.5 + 0.5) * rect.width + rect.left,
      y: (-v.y * 0.5 + 0.5) * rect.height + rect.top,
    };
  }

  function update(match, input, dt) {
    fpsAcc += dt;
    fpsN++;
    if (fpsAcc >= 0.4) {
      fps = Math.round(fpsN / fpsAcc);
      fpsAcc = 0;
      fpsN = 0;
    }
    follow(match, dt);
    if (shake > 0) {
      camera.position.y += Math.sin(performance.now() * 0.05) * shake;
      shake = Math.max(0, shake - dt * 1.6);
    }
    const controlled = match.players[match.controlled];
    for (const view of views) {
      const p = match.players[view.id];
      if (!p) continue;
      view.root.visible = p.on && !p.sent;
      view.root.position.set(p.x, 0, p.z);
      view.root.rotation.y = Math.PI / 2 - p.facing;
      const anim = p.kickT > 0.05 ? p.anim : p.anim;
      playAnim(view, anim || "idle");
      const sp = Math.hypot(p.vx, p.vz);
      view.mixer.timeScale = anim === "run" ? THREE.MathUtils.clamp(sp / 5.8, 0.75, 1.7) : 1;
      view.mixer.update(dt);
      view.blob.position.set(p.x, 0.03, p.z);
      const mine = p.id === match.controlled && match.humanTeam === p.team;
      view.ring.visible = mine;
      if (mine) view.ring.rotation.z += dt * 1.5;
    }
    if (views.ref) {
      const b = match.ball;
      views.ref.root.position.set(THREE.MathUtils.clamp(b.x - 6, 8, PITCH_L - 8), 0, THREE.MathUtils.clamp(b.z + 5, 6, PITCH_W - 6));
      views.ref.mixer.update(dt);
    }
    const b = match.ball;
    ball.mesh.position.set(b.x, Math.max(0.13, b.y), b.z);
    ball.mesh.rotation.z += b.vx * dt * 0.25;
    ball.mesh.rotation.x += b.vz * dt * 0.25;
    const speed = Math.hypot(b.vx, b.vz, b.vy);
    for (let i = trail.length - 1; i > 0; i--) {
      trail[i].position.copy(trail[i - 1].position);
      trail[i].visible = speed > 8;
    }
    trail[0].position.copy(ball.mesh.position);
    trail[0].visible = speed > 8;

    if (controlled && input.aim) {
      aimRing.visible = true;
      aimRing.position.set(input.aim.x, 0.06, input.aim.z);
    } else aimRing.visible = false;

    renderer.render(scene, camera);
    return fps;
  }

  function follow(match, dt) {
    const b = match.ball;
    const poss = b.holder != null ? match.players[b.holder].team : (b.kickerTeam ?? 0);
    const sign = poss === 0 ? 1 : -1;
    let eye;
    let look;
    if (mode === "follow") {
      eye = new THREE.Vector3(b.x - sign * 11, 5.2, b.z - 7);
      look = new THREE.Vector3(b.x + sign * 6, 1.1, b.z);
    } else if (mode === "goal") {
      const gx = poss === 0 ? PITCH_L : 0;
      eye = new THREE.Vector3(gx - sign * 16, 4.2, CZ + 10);
      look = new THREE.Vector3(gx, 1.4, CZ);
    } else if (mode === "tactical") {
      eye = new THREE.Vector3(b.x, 48, b.z + 0.2);
      look = new THREE.Vector3(b.x + sign * 4, 0, b.z);
    } else if (mode === "low") {
      eye = new THREE.Vector3(b.x - sign * 6, 2.2, b.z - 6);
      look = new THREE.Vector3(b.x + sign * 8, 1, b.z);
    } else {
      eye = new THREE.Vector3(b.x - sign * 1.5, 11.5, -13);
      look = new THREE.Vector3(b.x + sign * 16, 0.8, b.z * 0.4 + CZ * 0.6);
      if (b.x < 28) {
        eye = new THREE.Vector3(b.x - 12, 6.4, -6);
        look = new THREE.Vector3(6, 1.4, CZ);
      } else if (b.x > PITCH_L - 28) {
        eye = new THREE.Vector3(b.x + 12, 6.4, -6);
        look = new THREE.Vector3(PITCH_L - 6, 1.4, CZ);
      }
    }
    const k = 1 - Math.exp(-4.2 * Math.max(dt, 0.001));
    camPos.lerp(eye, k);
    camLook.lerp(look, k);
    camera.position.copy(camPos);
    camera.lookAt(camLook);
  }

  function punch(amount) { shake = Math.max(shake, amount); }
  function setMode(name) { if (MODELS.includes(name)) mode = name; }
  function cycleMode() {
    mode = MODELS[(MODELS.indexOf(mode) + 1) % MODELS.length];
    return mode;
  }

  return { spawn, update, groundAt, aimHigh, punch, setMode, cycleMode, resize, camera, get mode() { return mode; } };
}

function makePlayer(source, clips, p, kit) {
  const root = cloneSkeleton(source);
  root.traverse((o) => {
    if (!o.isMesh) return;
    o.castShadow = true;
    o.receiveShadow = true;
    o.material = o.material.clone();
    o.frustumCulled = false;
    const n = o.material.name;
    if (n === "Jersey" || n === "Socks") o.material.color.set(kit.jersey);
    if (n === "Shorts") o.material.color.set(kit.shorts);
    if (n === "Trim") o.material.color.set(kit.trim);
    if (n === "Boots") o.material.color.set("#141416");
  });
  const chest = root.getObjectByName("chest");
  if (chest && p.number) {
    const tag = numberPlate(p.number, kit.trim);
    tag.position.set(0, 0.02, -0.18);
    chest.add(tag);
  }
  const mixer = new THREE.AnimationMixer(root);
  const actions = {};
  Object.entries(clips).forEach(([name, clip]) => {
    const act = mixer.clipAction(clip);
    if (name !== "idle" && name !== "run") {
      act.setLoop(THREE.LoopOnce, 1);
      act.clampWhenFinished = true;
    }
    actions[name] = act;
  });
  actions.idle?.play();
  const blob = new THREE.Mesh(
    new THREE.CircleGeometry(0.42, 16),
    new THREE.MeshBasicMaterial({ color: 0x04140c, transparent: true, opacity: 0.35, depthWrite: false })
  );
  blob.rotation.x = -Math.PI / 2;
  root.parent && blob; // attached by caller via scene
  const ring = new THREE.Mesh(
    new THREE.RingGeometry(0.55, 0.68, 28),
    new THREE.MeshBasicMaterial({ color: 0xffd25a, side: THREE.DoubleSide })
  );
  ring.rotation.x = -Math.PI / 2;
  ring.position.y = 0.04;
  ring.visible = false;
  root.add(ring);
  return { id: p.id, root, mixer, actions, current: "idle", blob, ring };
}

function playAnim(view, name) {
  const next = view.actions[name] || view.actions.idle;
  if (!next || view.current === name) return;
  const prev = view.actions[view.current];
  if (prev && prev !== next) prev.fadeOut(0.12);
  next.reset().fadeIn(0.1).play();
  view.current = name;
}

function numberPlate(num, trim) {
  const c = document.createElement("canvas");
  c.width = 128;
  c.height = 128;
  const g = c.getContext("2d");
  g.clearRect(0, 0, 128, 128);
  g.fillStyle = "rgba(0,0,0,0.25)";
  g.fillRect(24, 28, 80, 72);
  g.fillStyle = trim || "#fff";
  g.font = "700 64px Rajdhani, sans-serif";
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.fillText(String(num), 64, 66);
  const tex = new THREE.CanvasTexture(c);
  const mesh = new THREE.Mesh(
    new THREE.PlaneGeometry(0.34, 0.34),
    new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthWrite: false })
  );
  return mesh;
}

function buildBall() {
  const c = document.createElement("canvas");
  c.width = 256;
  c.height = 256;
  const g = c.getContext("2d");
  g.fillStyle = "#f4f1ea";
  g.fillRect(0, 0, 256, 256);
  g.strokeStyle = "#c0392b";
  g.lineWidth = 6;
  g.beginPath();
  g.arc(128, 128, 70, 0, Math.PI * 2);
  g.stroke();
  g.beginPath();
  g.moveTo(20, 128);
  g.bezierCurveTo(80, 40, 176, 40, 236, 128);
  g.stroke();
  g.beginPath();
  g.moveTo(20, 128);
  g.bezierCurveTo(80, 216, 176, 216, 236, 128);
  g.stroke();
  const tex = new THREE.CanvasTexture(c);
  const mesh = new THREE.Mesh(
    new THREE.SphereGeometry(0.11, 24, 16),
    new THREE.MeshStandardMaterial({ map: tex, roughness: 0.42, metalness: 0.02 })
  );
  mesh.castShadow = true;
  return { mesh };
}

function buildTrail() {
  const mat = new THREE.MeshBasicMaterial({ color: 0xfff6e4, transparent: true, opacity: 0.35, depthWrite: false });
  return Array.from({ length: 6 }, (_, i) => {
    const m = new THREE.Mesh(new THREE.SphereGeometry(0.07 - i * 0.008, 8, 6), mat.clone());
    m.material.opacity = 0.28 - i * 0.04;
    m.visible = false;
    return m;
  });
}

function buildSky(scene) {
  const geo = new THREE.SphereGeometry(280, 32, 20);
  const mat = new THREE.ShaderMaterial({
    side: THREE.BackSide,
    depthWrite: false,
    vertexShader: "varying vec3 vP; void main(){ vP = position; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }",
    fragmentShader: `precision highp float;
      varying vec3 vP;
      void main() {
        float h = normalize(vP).y;
        vec3 top = vec3(0.025, 0.04, 0.10);
        vec3 mid = vec3(0.10, 0.14, 0.28);
        vec3 hor = vec3(0.92, 0.46, 0.22);
        vec3 col = mix(hor, mid, smoothstep(0.02, 0.22, h));
        col = mix(col, top, smoothstep(0.22, 0.75, h));
        gl_FragColor = vec4(col, 1.0);
      }`,
  });
  scene.add(new THREE.Mesh(geo, mat));
}

function buildPitch(scene) {
  const canvas = document.createElement("canvas");
  canvas.width = 2048;
  canvas.height = 1280;
  const g = canvas.getContext("2d");
  for (let i = 0; i < 26; i++) {
    g.fillStyle = i % 2 === 0 ? "#1c7a38" : "#176832";
    g.fillRect((i * canvas.width) / 26, 0, canvas.width / 26 + 1, canvas.height);
  }
  const img = g.getImageData(0, 0, canvas.width, canvas.height);
  for (let i = 0; i < img.data.length; i += 16) {
    const n = (Math.random() - 0.5) * 18;
    img.data[i] += n;
    img.data[i + 1] += n * 1.2;
    img.data[i + 2] += n * 0.4;
  }
  g.putImageData(img, 0, 0);
  // Worn mouths
  g.fillStyle = "rgba(12, 70, 28, 0.45)";
  g.beginPath();
  g.ellipse(40, canvas.height / 2, 70, 90, 0, 0, Math.PI * 2);
  g.fill();
  g.beginPath();
  g.ellipse(canvas.width - 40, canvas.height / 2, 70, 90, 0, 0, Math.PI * 2);
  g.fill();
  const tex = new THREE.CanvasTexture(canvas);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  const mesh = new THREE.Mesh(
    new THREE.PlaneGeometry(PITCH_L, PITCH_W),
    new THREE.MeshStandardMaterial({ map: tex, roughness: 0.86, metalness: 0.0 })
  );
  mesh.rotation.x = -Math.PI / 2;
  mesh.position.set(PITCH_L / 2, 0, CZ);
  mesh.receiveShadow = true;
  scene.add(mesh);

  const apron = new THREE.Mesh(
    new THREE.PlaneGeometry(220, 150),
    new THREE.MeshStandardMaterial({ color: 0x14361f, roughness: 1 })
  );
  apron.rotation.x = -Math.PI / 2;
  apron.position.set(PITCH_L / 2, -0.02, CZ);
  apron.receiveShadow = true;
  scene.add(apron);

  const lineMat = new THREE.MeshStandardMaterial({ color: 0xf3f4ee, roughness: 0.6 });
  const gold = new THREE.MeshStandardMaterial({ color: 0xffc84a, roughness: 0.45, emissive: 0x3a2500, emissiveIntensity: 0.25 });
  const add = (x1, z1, x2, z2, w = 0.12, mat = lineMat) => {
    const dx = x2 - x1;
    const dz = z2 - z1;
    const len = Math.hypot(dx, dz);
    const box = new THREE.Mesh(new THREE.BoxGeometry(len, 0.025, w), mat);
    box.position.set((x1 + x2) / 2, 0.03, (z1 + z2) / 2);
    box.rotation.y = Math.atan2(dz, dx);
    box.receiveShadow = true;
    scene.add(box);
  };
  add(0, 0, PITCH_L, 0);
  add(0, PITCH_W, PITCH_L, PITCH_W);
  add(0, 0, 0, PITCH_W);
  add(PITCH_L, 0, PITCH_L, PITCH_W);
  add(PITCH_L / 2, 0, PITCH_L / 2, PITCH_W);
  for (const d of [13, 20, 45]) {
    add(d, 0, d, PITCH_W);
    add(PITCH_L - d, 0, PITCH_L - d, PITCH_W);
  }
  for (const gx of [0, PITCH_L]) {
    const s = gx === 0 ? 1 : -1;
    add(gx, CZ - 7, gx + s * 4.5, CZ - 7);
    add(gx, CZ + 7, gx + s * 4.5, CZ + 7);
    add(gx + s * 4.5, CZ - 7, gx + s * 4.5, CZ + 7);
    add(gx, CZ - 9.5, gx + s * 13, CZ - 9.5);
    add(gx, CZ + 9.5, gx + s * 13, CZ + 9.5);
    add(gx + s * 13, CZ - 9.5, gx + s * 13, CZ + 9.5);
    arc(scene, gx, gold);
  }
}

function arc(scene, gx, mat) {
  const pts = [];
  for (let i = 0; i <= 28; i++) {
    const th = Math.PI * i / 28;
    const x = gx < 1 ? ARC * Math.sin(th) : PITCH_L - ARC * Math.sin(th);
    const z = CZ - ARC * Math.cos(th);
    pts.push(new THREE.Vector3(x, 0.04, z));
  }
  const geo = new THREE.BufferGeometry().setFromPoints(pts);
  scene.add(new THREE.Line(geo, new THREE.LineBasicMaterial({ color: 0xffc84a })));
  // A second thicker ribbon so the arc reads on a broadcast camera.
  for (let i = 0; i < pts.length - 1; i++) {
    const a = pts[i];
    const b = pts[i + 1];
    const len = a.distanceTo(b);
    const box = new THREE.Mesh(new THREE.BoxGeometry(len, 0.02, 0.16), mat);
    box.position.copy(a).add(b).multiplyScalar(0.5);
    box.rotation.y = Math.atan2(b.z - a.z, b.x - a.x);
    scene.add(box);
  }
}

function buildGoals(scene) {
  const white = new THREE.MeshStandardMaterial({ color: 0xf7f7f7, roughness: 0.35, metalness: 0.15 });
  const netMat = new THREE.MeshBasicMaterial({ color: 0xd5d8dc, transparent: true, opacity: 0.45, side: THREE.DoubleSide });
  for (const gx of [0, PITCH_L]) {
    const back = gx < 1 ? -1.5 : 1.5;
    for (const z of [CZ - GOAL_W, CZ + GOAL_W]) {
      const post = new THREE.Mesh(new THREE.CylinderGeometry(0.055, 0.055, 8, 12), white);
      post.position.set(gx, 4, z);
      post.castShadow = true;
      scene.add(post);
    }
    const bar = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, GOAL_W * 2, 10), white);
    bar.rotation.z = Math.PI / 2;
    bar.position.set(gx, BAR, CZ);
    scene.add(bar);
    const net = new THREE.Mesh(new THREE.PlaneGeometry(GOAL_W * 2, BAR), netMat);
    net.position.set(gx + back * 0.15, BAR / 2, CZ);
    scene.add(net);
    for (let i = 0; i <= 6; i++) {
      const z = CZ - GOAL_W + (i * GOAL_W * 2) / 6;
      const line = new THREE.Mesh(new THREE.CylinderGeometry(0.012, 0.012, Math.hypot(BAR, 1.5), 4), netMat);
      line.position.set(gx + back * 0.5, BAR * 0.45, z);
      line.rotation.z = gx < 1 ? 0.4 : -0.4;
      scene.add(line);
    }
  }
}

function buildStadium(scene) {
  const concrete = new THREE.MeshStandardMaterial({ color: 0x2a3038, roughness: 0.85 });
  const seatGeo = new THREE.BoxGeometry(1.15, 0.42, 0.7);
  // Far stand
  bowl(scene, -4, PITCH_L + 4, 96, 118, 11, 42, concrete, seatGeo, true);
  // Ends, kept clear of the camera on the near sideline.
  bowl(scene, -18, -6, 8, 82, 7, 16, concrete, seatGeo, false);
  bowl(scene, PITCH_L + 6, PITCH_L + 18, 8, 82, 7, 16, concrete, seatGeo, false);
  const roof = new THREE.Mesh(new THREE.BoxGeometry(PITCH_L + 24, 0.35, 16), new THREE.MeshStandardMaterial({ color: 0x1b2028, roughness: 0.5, metalness: 0.2 }));
  roof.position.set(PITCH_L / 2, 13.2, 108);
  scene.add(roof);
  const trim = new THREE.Mesh(new THREE.BoxGeometry(PITCH_L + 24, 0.12, 0.35), new THREE.MeshStandardMaterial({ color: 0xe8bc4e, emissive: 0x5a3e10, emissiveIntensity: 0.4 }));
  trim.position.set(PITCH_L / 2, 12.6, 100.2);
  scene.add(trim);

  const colors = [0x123c30, 0x8c2024, 0x183060, 0xaa781c, 0x202024];
  const names = ["PEIL PARK", "SAFFRON", "WESTWAVE", "BOG OAK", "LINEN BANK", "HILL ENERGY"];
  for (let i = 0; i < 12; i++) {
    const board = new THREE.Mesh(
      new THREE.BoxGeometry(PITCH_L / 12 - 0.2, 1.05, 0.12),
      new THREE.MeshStandardMaterial({ map: boardTex(names[i % names.length]), color: colors[i % colors.length], roughness: 0.6 })
    );
    board.position.set((i + 0.5) * (PITCH_L / 12), 0.62, PITCH_W + 1.1);
    scene.add(board);
  }
}

function boardTex(label) {
  const c = document.createElement("canvas");
  c.width = 512;
  c.height = 128;
  const g = c.getContext("2d");
  g.fillStyle = "#10141c";
  g.fillRect(0, 0, 512, 128);
  g.fillStyle = "#f4efe4";
  g.font = "600 48px Rajdhani, sans-serif";
  g.textAlign = "center";
  g.textBaseline = "middle";
  g.fillText(label, 256, 64);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

function bowl(scene, x0, x1, z0, z1, rows, cols, concrete, seatGeo, alongX) {
  const base = new THREE.Mesh(
    new THREE.BoxGeometry(Math.abs(x1 - x0), 1.1, Math.abs(z1 - z0)),
    concrete
  );
  base.position.set((x0 + x1) / 2, 0.4, (z0 + z1) / 2);
  base.receiveShadow = true;
  scene.add(base);
  const count = rows * cols;
  const mat = new THREE.MeshStandardMaterial({ roughness: 0.7, vertexColors: false });
  const seats = new THREE.InstancedMesh(seatGeo, mat, count);
  const dummy = new THREE.Object3D();
  const color = new THREE.Color();
  let n = 0;
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const u = (c + 0.5) / cols;
      const x = alongX ? x0 + (x1 - x0) * u : (x0 + x1) / 2 + (r * 0.85) * Math.sign(x0 < 0 ? -1 : 1);
      const z = alongX ? z0 + 1.2 + r * 1.15 : z0 + (z1 - z0) * u;
      dummy.position.set(x, 1.15 + r * 0.55, z);
      dummy.rotation.set(0, alongX ? 0 : Math.PI / 2, 0);
      dummy.updateMatrix();
      seats.setMatrixAt(n, dummy.matrix);
      const hue = (c * 0.07 + r * 0.04) % 1;
      color.setHSL(hue, 0.45, 0.38 + ((c + r) % 3) * 0.04);
      seats.setColorAt(n, color);
      n++;
    }
  }
  if (seats.instanceColor) seats.instanceColor.needsUpdate = true;
  seats.castShadow = false;
  seats.receiveShadow = true;
  scene.add(seats);
}

function buildLights(scene) {
  scene.add(new THREE.HemisphereLight(0x9eb6e8, 0x1c3a22, 0.55));
  const sun = new THREE.DirectionalLight(0xfff0d2, 1.55);
  sun.position.set(40, 48, -30);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.camera.left = -90;
  sun.shadow.camera.right = 110;
  sun.shadow.camera.top = 80;
  sun.shadow.camera.bottom = -80;
  sun.shadow.camera.near = 8;
  sun.shadow.camera.far = 180;
  sun.shadow.bias = -0.00035;
  scene.add(sun);
  scene.add(sun.target);
  sun.target.position.set(72, 0, 45);

  for (const [x, z] of [[-6, -4], [PITCH_L + 6, -4], [-6, PITCH_W + 6], [PITCH_L + 6, PITCH_W + 6]]) {
    const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.16, 22, 8), new THREE.MeshStandardMaterial({ color: 0xc8ccd2, metalness: 0.6, roughness: 0.35 }));
    pole.position.set(x, 11, z);
    scene.add(pole);
    const head = new THREE.Mesh(new THREE.BoxGeometry(1.6, 0.28, 0.5), new THREE.MeshStandardMaterial({ color: 0xfff1c8, emissive: 0xffe2a0, emissiveIntensity: 2.2 }));
    head.position.set(x, 22, z);
    scene.add(head);
    const spot = new THREE.SpotLight(0xfff0d0, 28, 90, 0.7, 0.55, 1);
    spot.position.set(x, 22, z);
    spot.target.position.set(PITCH_L / 2, 0, CZ);
    scene.add(spot);
    scene.add(spot.target);
  }
}
