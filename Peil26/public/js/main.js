import * as THREE from "three";
import { createWorld } from "./world.js";
import { createInput, padStatus } from "./input.js";
import { COUNTIES, createMatch, step, clockStr, controlled, attackGoal } from "./sim.js";

const canvas = document.getElementById("view");
const hud = document.getElementById("hud");
const menu = document.getElementById("menu");
const menuBody = document.getElementById("menuBody");
const menuTag = document.getElementById("menuTag");
const menuFoot = document.getElementById("menuFoot");
const loading = document.getElementById("loading");
const toast = document.getElementById("toast");

const RULES = `2026 men's exhibition rules. Not a GAA product.

Goal 3. Point 1. Two-pointer adds 2 if the kick is struck on or outside the 40-metre arc, and no teammate touches it. A hand-pass over the bar is not a score. A fist into the net is a goal.

Four steps, then solo or release. One bounce until you solo. Solo-and-go after a foul. Kick-out from the 20. Advanced mark inside the opposition 20.

Keep 4 in your own half and 3 inside the opposition 45. Black card is 10 minutes in the sin bin, no substitute. The hooter ends the half unless the ball is already in flight.`;

const CONTROLS = `KEYBOARD
WASD move. Mouse aims. Hold Space, release to kick.
Q hand pass. E fist. F solo. R bounce. H hook.
X tackle. Z block. V sidestep. C switch. G mark.
1-5 camera. Esc pause. M mute. F11 fullscreen.

USB / EASYSMX
Plug in the USB cable or the 2.4G receiver.
XInput mode (often LED 1 and 4) uses the Xbox layout.
D-Input still works. Back + Start swaps Xbox / Nintendo face buttons.

Left stick or D-pad  move
A or RT             kick, hold for power
LT                  driven goal. Otherwise aim over the bar
X hand   Y solo   B bounce
LB tackle   RB sprint
Right stick aim   click hook
Back switch   Start pause`;

const state = {
  screen: "title",
  index: 0,
  home: 0,
  away: 1,
  you: 0,
  level: 1,
  length: 0,
  match: null,
  attract: null,
};

const LENGTHS = [
  ["Quick  ·  8 minutes", 8, 8],
  ["League clock  ·  35 minutes", 35, 6],
];
const LEVELS = ["easy", "medium", "hard"];

const input = createInput();
let world;
let last = performance.now();
let acc = 0;
let toastT = 0;

const forward = new THREE.Vector3();
const right = new THREE.Vector3();

boot();

async function boot() {
  try {
    if (document.fonts) await document.fonts.load("28px Rajdhani");
  } catch (err) { /* canvas numbers fall back */ }
  try {
  world = await createWorld(canvas);
  state.attract = createMatch({ humanTeam: null, live: true, seed: 26, halfMinutes: 10, timeScale: 10 });
  world.spawn(state.attract);
  loading.style.display = "none";
  showMenu();
  requestAnimationFrame(frame);
  } catch (err) {
    loading.style.display = "grid";
    loading.textContent = "3D view failed: " + (err && err.message ? err.message : err);
    console.error(err);
  }
}

function frame(now) {
  const dt = Math.min(0.05, (now - last) / 1000);
  last = now;
  const raw = input.poll(dt);
  if (raw.muteEdge) document.getElementById("hud").style.filter = document.getElementById("hud").style.filter ? "" : "grayscale(0.2)";
  if (raw.fullEdge && document.fullscreenElement) document.exitFullscreen();
  else if (raw.fullEdge) document.body.requestFullscreen?.();
  if (raw.layoutFlip) flash(`Face buttons: ${raw.layout === "xbox" ? "Xbox" : "Nintendo"}`);

  applyCameraMove(raw);
  applyAim(raw);

  acc += dt;
  const simDt = 1 / 60;
  while (acc >= simDt) {
    tick(simDt, raw);
    acc -= simDt;
  }
  const shown = state.screen === "play" || state.screen === "pause" ? state.match : state.attract;
  if (shown) {
    const fps = world.update(shown, raw, dt);
    document.getElementById("fps").textContent = `${fps} FPS`;
    if (state.screen === "play" || state.screen === "pause") paintHud(shown, raw);
  }
  if (toastT > 0) {
    toastT -= dt;
    if (toastT <= 0) toast.style.display = "none";
  }
  requestAnimationFrame(frame);
}

function tick(dt, raw) {
  if (state.screen === "title" || state.screen === "teams" || state.screen === "rules" || state.screen === "controls") {
    if (state.attract) step(state.attract, dt, { moveX: 0, moveZ: 0 });
    if (raw.menuUp) { state.index--; nav(); }
    if (raw.menuDown) { state.index++; nav(); }
    if (raw.menuLeft) change(-1);
    if (raw.menuRight) change(1);
    if (raw.confirm) activate();
    if (raw.cancel && state.screen !== "title") { state.screen = "title"; state.index = 0; showMenu(); }
    return;
  }
  if (state.screen === "pause") {
    if (raw.menuUp) { state.index--; nav(); }
    if (raw.menuDown) { state.index++; nav(); }
    if (raw.confirm) activate();
    if (raw.cancel || raw.pause) { state.screen = "play"; menu.classList.remove("show"); }
    return;
  }
  const m = state.match;
  if (!m) return;
  if (raw.pause && m.phase === "open") {
    state.screen = "pause";
    state.index = 0;
    showMenu();
    return;
  }
  if (raw.camera) world.setMode(["broadcast", "follow", "goal", "tactical", "low"][raw.camera - 1]);
  step(m, dt, raw);
  if (m.bannerKind === "goal") world.punch(0.35);
  if (m.bannerKind === "two") world.punch(0.18);
  if (m.phase === "fulltime" && raw.confirm) toTitle();
}

function applyCameraMove(raw) {
  world.camera.getWorldDirection(forward);
  forward.y = 0;
  if (forward.lengthSq() < 0.001) forward.set(0, 0, 1);
  forward.normalize();
  right.set(forward.z, 0, -forward.x);
  const ix = raw.moveX;
  const iz = raw.moveZ;
  raw.moveX = right.x * ix + forward.x * iz;
  raw.moveZ = right.z * ix + forward.z * iz;
}

function applyAim(raw) {
  const m = state.screen === "play" ? state.match : null;
  const p = m ? controlled(m) : null;
  const stick = Math.hypot(raw.aimStickX, raw.aimStickZ);
  if (p && stick > 0.22) {
    raw.aim = {
      x: p.x + right.x * raw.aimStickX * 26 + forward.x * raw.aimStickZ * 26,
      z: p.z + right.z * raw.aimStickX * 26 + forward.z * raw.aimStickZ * 26,
    };
    raw.aimHigh = !raw.lowShot;
    return;
  }
  const g = world.groundAt(raw.mouseX, raw.mouseY);
  if (g) raw.aim = g;
  if (p && raw.mouseMoved) raw.aimHigh = world.aimHigh(raw.mouseX, raw.mouseY, attackGoal(p.team));
  else if (p && raw.padName && !raw.mouseMoved) {
    raw.aim = { x: attackGoal(p.team), z: 45 };
    raw.aimHigh = !raw.lowShot;
  }
}

function nav() {
  const n = items().length || 1;
  state.index = (state.index + n) % n;
  showMenu();
}

function items() {
  if (state.screen === "title") return ["Play match", "Rules of 2026", "Controls", "Quit"];
  if (state.screen === "teams") return [
    `Home     ${COUNTIES[state.home].name}`,
    `Away     ${COUNTIES[state.away].name}`,
    `Level    ${LEVELS[state.level]}`,
    `Clock    ${LENGTHS[state.length][0]}`,
    `You play ${COUNTIES[state.you === 0 ? state.home : state.away].name}`,
    "Start match",
  ];
  if (state.screen === "pause") return ["Resume", "Camera", "Quit to menu"];
  return [];
}

function change(dir) {
  if (state.screen !== "teams") return;
  if (state.index === 0) state.home = (state.home + dir + COUNTIES.length) % COUNTIES.length;
  if (state.index === 1) state.away = (state.away + dir + COUNTIES.length) % COUNTIES.length;
  if (state.index === 2) state.level = (state.level + dir + 3) % 3;
  if (state.index === 3) state.length = (state.length + dir + LENGTHS.length) % LENGTHS.length;
  if (state.index === 4) state.you = 1 - state.you;
  if (state.home === state.away) state.away = (state.away + 1) % COUNTIES.length;
  showMenu();
}

function activate() {
  if (state.screen === "title") {
    if (state.index === 0) { state.screen = "teams"; state.index = 0; showMenu(); }
    else if (state.index === 1) { state.screen = "rules"; showMenu(); }
    else if (state.index === 2) { state.screen = "controls"; showMenu(); }
    else window.close();
  } else if (state.screen === "teams" && state.index === 5) startMatch();
  else if (state.screen === "pause") {
    if (state.index === 0) { state.screen = "play"; menu.classList.remove("show"); }
    else if (state.index === 1) flash(`Camera: ${world.cycleMode()}`);
    else toTitle();
  }
}

function startMatch() {
  const [label, minutes, scale] = LENGTHS[state.length];
  state.match = createMatch({
    home: COUNTIES[state.home].name,
    away: COUNTIES[state.away].name,
    humanTeam: state.you,
    difficulty: LEVELS[state.level],
    halfMinutes: minutes,
    timeScale: scale,
    seed: (Date.now() % 10000) || 7,
  });
  world.spawn(state.match);
  state.screen = "play";
  menu.classList.remove("show");
  hud.style.display = "block";
}

function toTitle() {
  state.screen = "title";
  state.index = 0;
  state.match = null;
  world.spawn(state.attract);
  showMenu();
}

function showMenu() {
  menu.classList.add("show");
  hud.style.display = state.screen === "pause" ? "block" : "none";
  const list = items();
  if (state.screen === "rules" || state.screen === "controls") {
    menuTag.textContent = state.screen === "rules" ? "RULES" : "CONTROLS";
    menuBody.innerHTML = `<div id="rules">${state.screen === "rules" ? RULES : CONTROLS}</div>`;
  } else {
    menuTag.textContent = state.screen === "teams" ? "EXHIBITION AT PEIL PARK" : state.screen === "pause" ? "PAUSED" : "GAELIC FOOTBALL · 2026 RULES";
    menuBody.innerHTML = list.map((line, i) => `<button class="item${i === state.index ? " on" : ""}" data-i="${i}">${i === state.index ? ">  " : "    "}${line}</button>`).join("");
    menuBody.querySelectorAll("button").forEach((b) => {
      b.onclick = () => { state.index = Number(b.dataset.i); activate(); };
    });
  }
  const pad = padStatus();
  menuFoot.textContent = pad.padName
    ? `${pad.padKind}  ·  ${pad.padName}  ·  ${pad.layout} layout`
    : "Plug in a USB or EasySMX pad. Keyboard still works.";
}

function paintHud(m, raw) {
  const a = m.teams[0];
  const b = m.teams[1];
  document.getElementById("scoreA").textContent = `${a.score()}  (${a.total()})`;
  document.getElementById("scoreB").textContent = `${b.score()}  (${b.total()})`;
  document.getElementById("crestA").textContent = a.short;
  document.getElementById("crestB").textContent = b.short;
  document.getElementById("crestA").style.background = a.jersey;
  document.getElementById("crestB").style.background = b.jersey;
  document.getElementById("crestA").style.color = "#111";
  document.getElementById("crestB").style.color = "#111";
  document.getElementById("clock").textContent = clockStr(m);
  document.getElementById("period").textContent = `${(m.period || "First half").toUpperCase()}  ·  PEIL PARK`;
  const p = controlled(m);
  document.getElementById("who").textContent = p ? `${p.number}  ${p.name}` : "";
  document.getElementById("stamina").firstElementChild.style.width = `${Math.round((p?.stamina || 0) * 100)}%`;
  document.getElementById("hint").textContent = m.hint;
  document.getElementById("pad").textContent = raw.padName ? `${raw.padKind} · ${raw.layout}` : "";
  const banner = document.getElementById("banner");
  if (m.bannerT > 0) {
    banner.classList.add("show");
    const color = { goal: "#ffd05a", two: "#ffb030", point: "#f4f1ea", black: "#f2f2f2", penalty: "#ffd05a" }[m.bannerKind] || "#f4f1ea";
    banner.style.color = color;
    banner.innerHTML = `${m.banner}${m.bannerSub ? `<small>${m.bannerSub}</small>` : ""}`;
  } else banner.classList.remove("show");
  const power = document.getElementById("power");
  if (m.charge > 0.02) {
    power.classList.add("show");
    power.firstElementChild.style.width = `${Math.round(m.charge * 100)}%`;
  } else power.classList.remove("show");
}

function flash(text) {
  toast.textContent = text;
  toast.style.display = "block";
  toastT = 1.6;
}
