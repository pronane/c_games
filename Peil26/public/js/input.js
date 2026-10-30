// Keyboard, mouse and USB pads. EasySMX in XInput uses the standard map.
// D-Input / generic USB pads use the community EasySMX button order.

const DEAD = 0.16;
const prevBtn = {};
let lastPad = { padName: "", padKind: "", layout: "xbox" };

export function padStatus() {
  return lastPad;
}

const STANDARD = { a: 0, b: 1, x: 2, y: 3, lb: 4, rb: 5, lt: 6, rt: 7, back: 8, start: 9, l3: 10, r3: 11, up: 12, down: 13, left: 14, right: 15 };
// Windows EasySMX / generic USB gamepad: Y B A X, shoulders, triggers as buttons, hat often arrives as buttons 12-15 too.
const EASYSMX = { a: 2, b: 1, x: 3, y: 0, lb: 4, rb: 5, lt: 6, rt: 7, back: 8, start: 9, l3: 10, r3: 11, up: 12, down: 13, left: 14, right: 15 };

export function createInput() {
  const keys = new Set();
  const just = new Set();
  const mouse = { x: 0, y: 0, dx: 0, dy: 0, left: false, right: false, click: false };
  let layout = "xbox";
  let padName = "";
  let padKind = "";
  let navT = 0;
  const state = blank();

  window.addEventListener("keydown", (e) => {
    if (["Space", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Tab"].includes(e.code)) e.preventDefault();
    if (!keys.has(e.code)) just.add(e.code);
    keys.add(e.code);
    if (e.code === "KeyM") state.muteEdge = true;
    if (e.code === "F11") { e.preventDefault(); state.fullEdge = true; }
  });
  window.addEventListener("keyup", (e) => keys.delete(e.code));
  window.addEventListener("mousemove", (e) => {
    mouse.x = e.clientX;
    mouse.y = e.clientY;
    mouse.dx += e.movementX;
    mouse.dy += e.movementY;
  });
  window.addEventListener("mousedown", (e) => {
    if (e.button === 0) { mouse.left = true; mouse.click = true; }
    if (e.button === 2) mouse.right = true;
  });
  window.addEventListener("mouseup", (e) => {
    if (e.button === 0) mouse.left = false;
    if (e.button === 2) mouse.right = false;
  });
  window.addEventListener("contextmenu", (e) => e.preventDefault());
  window.addEventListener("gamepadconnected", (e) => {
    padName = cleanName(e.gamepad.id);
    padKind = kindOf(e.gamepad);
  });
  window.addEventListener("gamepaddisconnected", () => {
    padName = "";
    padKind = "";
  });

  function poll(dt, cameraAim) {
    const out = blank();
    out.muteEdge = state.muteEdge;
    out.fullEdge = state.fullEdge;
    state.muteEdge = false;
    state.fullEdge = false;

    const gp = activePad();
    if (gp) {
      padName = cleanName(gp.id);
      padKind = kindOf(gp);
    }
    out.padName = padName;
    out.padKind = padKind;
    out.layout = layout;
    lastPad = { padName, padKind, layout };

    let mx = (held("KeyD") || held("ArrowRight") ? 1 : 0) - (held("KeyA") || held("ArrowLeft") ? 1 : 0);
    let mz = (held("KeyW") || held("ArrowUp") ? 1 : 0) - (held("KeyS") || held("ArrowDown") ? 1 : 0);
    let rx = 0;
    let rz = 0;
    let padKick = false;
    let padKickEdge = false;
    let padKickUp = false;

    if (gp) {
      const map = buttonMap(gp);
      const lx = axis(gp, 0);
      const ly = axis(gp, 1);
      if (Math.hypot(lx, ly) > 0.05) {
        mx += lx;
        mz += -ly;
      }
      const hat = hatDir(gp, map);
      if (Math.hypot(lx, ly) < DEAD) {
        mx += hat.x;
        mz += hat.z;
      }
      if (gp.axes.length > 3 && gp.mapping === "standard") {
        rx = axis(gp, 2);
        rz = -axis(gp, 3);
      } else if (gp.axes.length > 4) {
        rx = axis(gp, 2);
        rz = -axis(gp, 3);
      }
      const btn = (name) => pressed(gp, map[name]);
      const edge = (name) => rising(gp, map[name]);
      const up = (name) => falling(gp, map[name]);
      if (layout === "nintendo") {
        // Physical bottom stays kick: swap the indices we already chose.
      }
      const A = layout === "xbox" ? "a" : "b";
      const B = layout === "xbox" ? "b" : "a";
      const X = layout === "xbox" ? "x" : "y";
      const Y = layout === "xbox" ? "y" : "x";
      padKick = btn(A) || trigger(gp, map.rt) > 0.35;
      padKickEdge = edge(A) || triggerRising(gp, map.rt);
      padKickUp = up(A) || triggerFalling(gp, map.rt);
      out.hand = edge(X) || just.has("KeyQ") || mouse.right;
      out.fist = just.has("KeyE") || (btn("rb") && edge(X));
      out.solo = edge(Y) || just.has("KeyF");
      out.bounce = edge(B) || just.has("KeyR");
      out.tackle = edge("lb") || just.has("KeyX");
      out.block = trigger(gp, map.lt) > 0.45 || held("KeyZ");
      out.sidestep = edge("l3") || just.has("KeyV");
      out.hook = edge("r3") || just.has("KeyH");
      out.switch = edge("back") || just.has("KeyC") || just.has("Tab");
      out.sprint = btn("rb") || held("ShiftLeft") || held("ShiftRight");
      out.pause = edge("start") || just.has("Escape");
      out.confirm = edge("start") || edge(A) || just.has("Enter");
      out.cancel = edge(B) || just.has("Escape");
      out.mark = (hat.z < 0 && edgeHat(gp, "down")) || just.has("KeyG");
      out.cameraNext = just.has("Digit1") ? 1 : 0;
      if (edge("back") && btn("start") || edge("start") && btn("back")) {
        layout = layout === "xbox" ? "nintendo" : "xbox";
        out.layout = layout;
        out.layoutFlip = true;
      }
      out.aimStickX = rx;
      out.aimStickZ = rz;
      out.lowShot = trigger(gp, map.lt) > 0.4;
      out.menuUp = hat.z > 0.5 && edgeHat(gp, "up") || ly < -0.55 && navReady(dt);
      out.menuDown = hat.z < -0.5 && edgeHat(gp, "down") || ly > 0.55 && navReady(dt);
      out.menuLeft = hat.x < -0.5 && edgeHat(gp, "left") || lx < -0.55 && navReady(dt);
      out.menuRight = hat.x > 0.5 && edgeHat(gp, "right") || lx > 0.55 && navReady(dt);
      remember(gp);
    } else {
      out.hand = just.has("KeyQ") || mouse.right;
      out.fist = just.has("KeyE");
      out.solo = just.has("KeyF");
      out.bounce = just.has("KeyR");
      out.tackle = just.has("KeyX");
      out.block = held("KeyZ");
      out.sidestep = just.has("KeyV");
      out.hook = just.has("KeyH");
      out.switch = just.has("KeyC") || just.has("Tab");
      out.sprint = held("ShiftLeft") || held("ShiftRight");
      out.pause = just.has("Escape");
      out.confirm = just.has("Enter");
      out.cancel = just.has("Escape");
      out.mark = just.has("KeyG");
      out.menuUp = just.has("ArrowUp") || just.has("KeyW");
      out.menuDown = just.has("ArrowDown") || just.has("KeyS");
      out.menuLeft = just.has("ArrowLeft") || just.has("KeyA");
      out.menuRight = just.has("ArrowRight") || just.has("KeyD");
    }

    if (!gp) {
      out.menuUp = out.menuUp || just.has("ArrowUp") || just.has("KeyW");
      out.menuDown = out.menuDown || just.has("ArrowDown") || just.has("KeyS");
      out.menuLeft = out.menuLeft || just.has("ArrowLeft") || just.has("KeyA");
      out.menuRight = out.menuRight || just.has("ArrowRight") || just.has("KeyD");
    } else {
      out.menuUp = out.menuUp || just.has("ArrowUp") || just.has("KeyW");
      out.menuDown = out.menuDown || just.has("ArrowDown") || just.has("KeyS");
      out.menuLeft = out.menuLeft || just.has("ArrowLeft");
      out.menuRight = out.menuRight || just.has("ArrowRight");
    }

    const len = Math.hypot(mx, mz);
    if (len > 1) { mx /= len; mz /= len; }
    out.moveX = mx;
    out.moveZ = mz;
    out.kickHeld = held("Space") || mouse.left || padKick;
    out.kickPressed = just.has("Space") || mouse.click || padKickEdge;
    out.kickReleased = (!held("Space") && state.spaceWas) || padKickUp;
    if (mouse.click && !padKick) {
      out.kickPressed = true;
      out.kickReleased = true;
      out.kickHeld = false;
    }
    state.spaceWas = held("Space") || padKick;
    out.aim = cameraAim || null;
    out.aimHigh = out.lowShot ? false : null;
    out.mouseX = mouse.x;
    out.mouseY = mouse.y;
    out.mouseMoved = Math.abs(mouse.dx) + Math.abs(mouse.dy) > 0;
    out.toArc = just.has("KeyY") || just.has("Digit2");

    for (let i = 1; i <= 5; i++) if (just.has(`Digit${i}`)) out.camera = i;

    just.clear();
    mouse.click = false;
    mouse.right = false;
    mouse.dx = 0;
    mouse.dy = 0;
    return out;
  }

  function navReady(dt) {
    navT -= dt;
    if (navT <= 0) { navT = 0.18; return true; }
    return false;
  }

  function held(code) { return keys.has(code); }

  return { poll, get layout() { return layout; } };
}

function blank() {
  return {
    moveX: 0, moveZ: 0, sprint: false,
    kickHeld: false, kickPressed: false, kickReleased: false,
    hand: false, fist: false, solo: false, bounce: false, hook: false,
    tackle: false, block: false, sidestep: false, switch: false, mark: false,
    confirm: false, cancel: false, pause: false, toArc: false,
    aim: null, aimHigh: null, aimStickX: 0, aimStickZ: 0, lowShot: false,
    menuUp: false, menuDown: false, menuLeft: false, menuRight: false,
    camera: 0, muteEdge: false, fullEdge: false, layoutFlip: false,
    padName: "", padKind: "", layout: "xbox", mouseX: 0, mouseY: 0, mouseMoved: false,
  };
}

function activePad() {
  const pads = navigator.getGamepads ? navigator.getGamepads() : [];
  let best = null;
  let score = -1;
  for (const gp of pads) {
    if (!gp) continue;
    let s = gp.buttons.length;
    const id = gp.id.toLowerCase();
    if (id.includes("easysmx") || id.includes("easy smx") || id.includes("esm-")) s += 40;
    if (id.includes("usb") || id.includes("xbox") || id.includes("xinput") || id.includes("gamepad") || id.includes("controller")) s += 8;
    if (gp.mapping === "standard") s += 6;
    if (s > score) { score = s; best = gp; }
  }
  return best;
}

function kindOf(gp) {
  const id = gp.id.toLowerCase();
  if (id.includes("easysmx") || id.includes("easy smx") || id.includes("esm-")) return gp.mapping === "standard" ? "EasySMX · XInput" : "EasySMX · USB";
  if (gp.mapping === "standard") return "USB gamepad";
  return "USB controller";
}

function cleanName(id) {
  return id.replace(/\s*\(.*?\)\s*/g, "").replace(/Vendor:.*$/, "").trim().slice(0, 42);
}

function buttonMap(gp) {
  if (gp.mapping === "standard") return STANDARD;
  return EASYSMX;
}

function axis(gp, i) {
  const v = gp.axes[i] || 0;
  if (Math.abs(v) < DEAD) return 0;
  const s = Math.sign(v);
  return s * (Math.abs(v) - DEAD) / (1 - DEAD);
}

function pressed(gp, i) {
  return !!(gp.buttons[i] && gp.buttons[i].pressed);
}

function rising(gp, i) {
  const now = pressed(gp, i);
  const was = !!prevBtn[i];
  return now && !was;
}

function falling(gp, i) {
  const now = pressed(gp, i);
  const was = !!prevBtn[i];
  return !now && was;
}

function remember(gp) {
  for (let i = 0; i < gp.buttons.length; i++) prevBtn[i] = gp.buttons[i].pressed;
  prevBtn.rt = trigger(gp, buttonMap(gp).rt);
}

function trigger(gp, index) {
  if (gp.buttons[index]) return gp.buttons[index].value || (gp.buttons[index].pressed ? 1 : 0);
  return 0;
}

function triggerRising(gp, index) {
  return trigger(gp, index) > 0.45 && (prevBtn.rt || 0) <= 0.45;
}
function triggerFalling(gp, index) {
  return trigger(gp, index) < 0.25 && (prevBtn.rt || 0) >= 0.25;
}

function hatDir(gp, map) {
  let x = 0;
  let z = 0;
  if (pressed(gp, map.up)) z += 1;
  if (pressed(gp, map.down)) z -= 1;
  if (pressed(gp, map.left)) x -= 1;
  if (pressed(gp, map.right)) x += 1;
  if (gp.axes.length >= 6 && gp.mapping !== "standard") {
    // Some USB pads report the hat as a pair of axes near the end.
  }
  return { x, z };
}

let prevHat = "";
function edgeHat(gp, dir) {
  const map = buttonMap(gp);
  const key = { up: map.up, down: map.down, left: map.left, right: map.right }[dir];
  return rising(gp, key);
}
