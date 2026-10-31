import { createMatch, cloneInput, neutralInput, HASH_EVERY, DEFAULT_DELAY } from './sim.mjs';
import { createPacer, stepBudget } from './pace.mjs';
import { evalStall, stallLabel, connectFailure, nextBackoff, isGameData, poorLink, CONNECT_TIMEOUT_MS, RECONNECT_HOLD_MS } from './stall.mjs';
import { encodeTail, encodeFrames, decodeInputs, absorbContig, gapBefore, unpackInput, unpackHist, packInput } from './wire.mjs';

const FIGHTERS = ['kairo', 'lyra', 'naomi', 'brutus', 'void', 'zap'];
const FNAME = { kairo: 'KAIRO', lyra: 'LYRA', naomi: 'NAOMI', brutus: 'BRUTUS', void: 'VOID', zap: 'ZAP' };
const STAGES = ['rooftop', 'temple', 'industrial'];
const SCREEN_W = 1280, SCREEN_H = 720, GROUND_Y = 560;
const SPEED = 240, JUMP = -520, GRAV = 1600;
const SIM_HZ = 60;
const SIM_DT = 1 / SIM_HZ;
const SIM_MS = 1000 / SIM_HZ;
const DUR = { idle: 6, walk: 4, crouch: 8, jump: 5, lp: 3, hp: 4, lk: 3, hk: 4, block: 8, throw: 4, hit: 5, special1: 4, special2: 3, super: 4, win: 6, lose: 8 };
const DMG = { lp: 6, hp: 12, lk: 7, hk: 11, throw: 14, special1: 15, special2: 16, super: 28 };
const JOIN_GIVE_UP_MS = 90000;

let META = null;
try { META = await fetch('./assets_hd/meta.json').then((r) => r.json()); } catch {}

const cv = document.getElementById('cv');
const ctx = cv.getContext('2d');
const netpill = document.getElementById('netpill');
const roompill = document.getElementById('roompill');
const timerEl = document.getElementById('timer');
const hpA = document.getElementById('hpA');
const hpB = document.getElementById('hpB');
const nameA = document.getElementById('nameA');
const nameB = document.getElementById('nameB');
const inviteEl = document.getElementById('invite');
const chargrid = document.getElementById('chargrid');
const statusEl = document.getElementById('status');
const pickInfo = document.getElementById('pickInfo');
const vsLine = document.getElementById('vsLine');
const quickBtn = document.getElementById('quickBtn');
const createBtn = document.getElementById('createBtn');
const joinBtn = document.getElementById('joinBtn');
const roomIn = document.getElementById('roomIn');
const copyBtn = document.getElementById('copyBtn');
const readyBtn = document.getElementById('readyBtn');
const leaveBtn = document.getElementById('leaveBtn');
const screens = { lobby: document.getElementById('lobby'), gameScr: document.getElementById('gameScr') };

let ws = null;
let room = null;
let slot = -1;
let picks = {};
let pingMs = 0;
const proto = location.protocol === 'https:' ? 'wss' : 'ws';
// Per-tab id. sessionStorage survives a reload of this tab and is not shared
// with a second tab, so the second tab cannot take this tab's slot.
let userId = sessionStorage.getItem('hd2_tabId');
let lastRoom = localStorage.getItem('hd2_room');
if (!userId) {
  const bytes = new Uint8Array(6);
  if (typeof crypto !== 'undefined' && crypto.getRandomValues) crypto.getRandomValues(bytes);
  else for (let i = 0; i < bytes.length; i++) bytes[i] = (Date.now() + i * 17) & 255;
  userId = 't' + Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  sessionStorage.setItem('hd2_tabId', userId);
}

let myPick = null;
let peerPick = null;
let serverReady = { 0: false, 1: false };
let occupied = { 0: false, 1: false };
let fighters = [null, null];
let sim = null;
let inputLog = [];
let sentFrames = new Set();
let peerAck = -1;
let remoteMax = -1;
let lastInputSend = 0;
let lastPeerRx = 0;
let lastHb = 0;
let lastNackAt = 0;
let lastNackFrom = -1;
let holdUntil = 0;
let selfHoldUntil = 0;
let connectTimer = null;
let socketJoined = false;
let stepTimes = [];
let remoteContig = -1;
let remoteHave = new Set();
let localInputs = new Map();
let rttSamples = [];
let connectFailedFast = false;
let driveMatch = null;
let localHashes = new Map();
let remoteHashes = new Map();
let lastHash = 0;
let raf = null;
let keys = {};
let touchInp = {};
let remoteKeys = {};
let fighterImgs = {};
let bgImg = new Image();
let midImg = new Image();
let fgImg = new Image();
let roomEpoch = 0;
let roomSeq = -1;
let outSeq = 0;
let readySeq = 0;
let remoteGen = null;
let remoteSeq = -1;
let pendingReady = false;
let pendingPick = null;
let joinAttempt = null;
let intentionalLeave = false;
let loadedFor = null;
let beganId = null;
let matchGen = 0;
const queue = [];

function wsURL() { return `${proto}://${location.host}`; }
function show(s) {
  for (const k in screens) screens[k].classList.remove('active');
  screens[s].classList.add('active');
}
function val(obj, i) {
  if (!obj) return undefined;
  return obj[i] != null ? obj[i] : obj[String(i)];
}
function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

function stamp(o) {
  const m = Object.assign({ userId }, o);
  if (m.t !== 'ping') {
    m.epoch = roomEpoch;
    if (m.seq == null) m.seq = ++outSeq;
  }
  return m;
}
function transmit(o) {
  if (!ws || ws.readyState !== 1) return false;
  ws.send(JSON.stringify(stamp(o)));
  return true;
}
function send(o) {
  if (o.t === 'pick') {
    pendingPick = o.char;
    if (room && ws && ws.readyState === 1) {
      pendingPick = null;
      transmit({ t: 'pick', char: o.char, userId });
    } else {
      connect();
    }
    return;
  }
  if (o.t === 'ready') {
    readySeq += 1;
    pendingReady = true;
    readyBtn.disabled = true;
    pickInfo.textContent = 'Ready! Waiting…';
    if (ws && ws.readyState === 1 && room) {
      pendingReady = false;
      transmit({ t: 'ready', ready: true, readySeq, userId });
      return;
    }
    const joining = joinAttempt || queue.some((m) => m.t === 'join' || m.t === 'create' || m.t === 'quick');
    if (ws && ws.readyState === 1 && !room && !joining) {
      pendingReady = false;
      transmit({ t: 'ready', ready: true, readySeq, userId });
      return;
    }
    connect();
    return;
  }
  if (ws && ws.readyState === 1) transmit(o);
  else {
    queue.push(o);
    connect();
  }
}
function maybeFlushReady() {
  if (!room || !ws || ws.readyState !== 1) return;
  // Pick has to land before ready, and both have to use the epoch from the join.
  if (pendingPick) {
    const char = pendingPick;
    pendingPick = null;
    transmit({ t: 'pick', char, userId });
  }
  if (!pendingReady) return;
  pendingReady = false;
  transmit({ t: 'ready', ready: true, readySeq, userId });
}
function flushQueue() {
  const first = [];
  const rest = [];
  for (const m of queue) {
    if (m.t === 'join' || m.t === 'create' || m.t === 'quick') first.push(m);
    else if (m.t === 'ready') pendingReady = true;
    else rest.push(m);
  }
  queue.length = 0;
  for (const m of first) transmit(m);
  if (joinAttempt && !first.some((m) => m.t === 'join' && m.room === joinAttempt.code)) {
    transmit({ t: 'join', room: joinAttempt.code, userId });
  }
  for (const m of rest) transmit(m);
}

function setOnline(on) {
  netpill.textContent = on ? 'online' : 'offline';
  netpill.style.background = on ? '#00d084' : '#0b1022';
  netpill.style.color = on ? '#000' : '';
}

function connect() {
  if (ws && ws.readyState === 1) return;
  if (ws && ws.readyState === 0) return;
  const started = Date.now();
  let opened = false;
  const sock = new WebSocket(wsURL());
  ws = sock;
  if (connectTimer) clearTimeout(connectTimer);
  connectTimer = setTimeout(() => {
    if (ws !== sock || sock.readyState !== 0) return;
    // Chromium can leave a socket in CONNECTING forever after many refusals.
    ws = null;
    try { sock.close(); } catch {}
  }, CONNECT_TIMEOUT_MS);
  sock.addEventListener('open', () => {
    if (ws !== sock) return;
    opened = true;
    connectFailedFast = false;
    if (connectTimer) clearTimeout(connectTimer);
    setOnline(true);
    flushQueue();
  });
  sock.addEventListener('close', () => {
    if (connectTimer) clearTimeout(connectTimer);
    if (ws === sock) ws = null;
    socketJoined = false;
    setOnline(false);
    if (!opened && Date.now() - started < 1500 && !(sim && !sim.closed)) classifyConnectFailure();
    if (intentionalLeave) return;
    if (sim && !sim.closed && !selfHoldUntil) selfHoldUntil = Date.now() + RECONNECT_HOLD_MS;
    const code = (joinAttempt && joinAttempt.code) || room || lastRoom;
    if (code && !joinAttempt) startJoin(String(code).toUpperCase());
  });
  sock.addEventListener('message', (e) => {
    if (ws !== sock) return;
    onMsg(e);
  });
}

let pingTimer = null;
let lastPingAt = 0;
function ensurePing() {
  if (pingTimer) return;
  pingTimer = setInterval(() => {
    if (!ws || ws.readyState !== 1) return;
    const now = Date.now();
    const gap = sim && !sim.closed ? 1000 : 250;
    if (now - lastPingAt < gap) return;
    lastPingAt = now;
    ws.send(JSON.stringify({ t: 'ping', ts: now }));
  }, 250);
}

function applyConnectFailure(kind) {
  const status = connectFailure(kind);
  connectFailedFast = !status.waking;
  if (!room && !intentionalLeave) {
    statusEl.textContent = status.text;
    if (status.clearPill) roompill.textContent = 'no room';
  }
}

function classifyConnectFailure() {
  fetch('/api/health', { cache: 'no-store' }).then((res) => {
    if (ws && ws.readyState === 1) return;
    // Any HTTP answer, including 503, means a host is there and waking.
    applyConnectFailure({ networkError: false, httpStatus: res.status });
  }).catch(() => {
    if (ws && ws.readyState === 1) return;
    applyConnectFailure({ networkError: true });
  });
}

function linkStatus(waitingLong) {
  if (connectFailedFast && !(ws && ws.readyState === 1)) return "Can't reach the server.";
  if (waitingLong) return 'Waking the server...';
  return 'Connecting…';
}

function stopJoin() {
  if (!joinAttempt) return;
  if (joinAttempt.timer) clearTimeout(joinAttempt.timer);
  joinAttempt = null;
}

function startJoin(code) {
  code = String(code || '').trim().toUpperCase();
  if (!code) return;
  if (joinAttempt && joinAttempt.code === code) return;
  stopJoin();
  const token = {};
  joinAttempt = { code, token, started: Date.now(), tries: 0, timer: null, waking: false };
  roomIn.value = code;
  const tick = () => {
    if (!joinAttempt || joinAttempt.token !== token) return;
    if (socketJoined && ws && ws.readyState === 1) {
      stopJoin();
      return;
    }
    if (Date.now() - joinAttempt.started > JOIN_GIVE_UP_MS) {
      statusEl.textContent = 'Could not reach the server. It can take about a minute to wake — try again.';
      stopJoin();
      syncReadyButton();
      return;
    }
    const open = ws && ws.readyState === 1;
    if (open) {
      if (!(sim && !sim.closed)) {
        statusEl.textContent = joinAttempt.waking ? `Waking the server... joining ${code}` : `Joining ${code}…`;
      }
      transmit({ t: 'join', room: code, userId });
    } else if (!ws || ws.readyState > 1) {
      const slow = Date.now() - joinAttempt.started > 1500;
      joinAttempt.waking = slow && !connectFailedFast;
      if (!(sim && !sim.closed)) statusEl.textContent = linkStatus(joinAttempt.waking);
      connect();
    }
    const wait = nextBackoff(joinAttempt.tries);
    joinAttempt.tries += 1;
    joinAttempt.timer = setTimeout(tick, wait);
  };
  if (!(sim && !sim.closed) && !(ws && ws.readyState === 1)) statusEl.textContent = linkStatus(false);
  tick();
}

function noteRoom(code, mySlot) {
  if (code) {
    room = code;
    lastRoom = code;
    localStorage.setItem('hd2_room', code);
    roompill.textContent = code;
    inviteEl.textContent = location.origin + location.pathname + '#' + code;
    try { history.replaceState(null, '', '#' + code); } catch {}
    leaveBtn.style.display = '';
    socketJoined = true;
    if (joinAttempt && joinAttempt.code === code) stopJoin();
  }
  if (typeof mySlot === 'number' && mySlot >= 0) {
    slot = mySlot;
    localStorage.setItem('hd2_slot', String(mySlot));
  }
}

function acceptMeta(m) {
  if (typeof m.epoch === 'number') {
    if (m.epoch < roomEpoch) return false;
    if (m.epoch > roomEpoch) {
      roomEpoch = m.epoch;
      remoteGen = null;
      remoteSeq = -1;
    }
  }
  if (typeof m.seq === 'number') {
    if (m.seq < roomSeq) return false;
    roomSeq = m.seq;
  }
  return true;
}

function syncReadyButton() {
  if (sim && !sim.closed) return;
  if (!room || (slot !== 0 && slot !== 1)) {
    readyBtn.disabled = true;
    pickInfo.textContent = myPick ? `You: ${FNAME[myPick]} — join a room, then Ready` : 'Pick a fighter';
    return;
  }
  if (serverReady[slot]) {
    readyBtn.disabled = true;
    pickInfo.textContent = 'Ready! Waiting…';
    return;
  }
  readyBtn.disabled = !myPick;
  pickInfo.textContent = myPick ? `You: ${FNAME[myPick]} — hit Ready` : 'Pick a fighter';
}

function updateRoomInfo() {
  const info = document.getElementById('roomInfo');
  if (!room) { info.style.display = 'none'; return; }
  const p0 = val(picks, 0);
  const p1 = val(picks, 1);
  const s0 = !!val(serverReady, 0);
  const s1 = !!val(serverReady, 1);
  const n0 = p0 ? (FNAME[p0] || p0) : '—';
  const n1 = p1 ? (FNAME[p1] || p1) : '—';
  const occ = (occupied[0] ? 1 : 0) + (occupied[1] ? 1 : 0);
  let txt = `Room ${room} — ${occ}/2`;
  txt += p0 ? ` | P1: ${n0} ${s0 ? '✅ Ready' : '…pick'}` : ' | P1: —';
  txt += p1 ? ` | P2: ${n1} ${s1 ? '✅ Ready' : '…pick'}` : ' | P2: —';
  if (s0 && s1) txt += ' — both Ready → starting…';
  info.textContent = txt;
  info.style.display = 'block';
}

function updateVS() {
  const p0 = val(picks, 0);
  const p1 = val(picks, 1);
  const s0 = !!val(serverReady, 0);
  const s1 = !!val(serverReady, 1);
  if (s0 && s1 && p0 && p1) {
    vsLine.style.display = 'block';
    vsLine.textContent = 'Both ready — starting…';
  } else if (myPick && p0 && p1) {
    const peer = slot === 1 ? p0 : p1;
    peerPick = peer;
    vsLine.style.display = 'block';
    vsLine.textContent = `VS  ${FNAME[myPick]} (You)  vs  ${FNAME[peer] || peer} — both picked, hit Ready`;
  } else {
    peerPick = null;
    vsLine.style.display = 'none';
    vsLine.textContent = '';
  }
  updateRoomInfo();
}

function highlightPick() {
  if (!myPick) return;
  for (const c of chargrid.children) c.classList.toggle('sel', c.dataset.char === myPick);
}

function applySnapshot(m) {
  if (!acceptMeta(m)) return false;
  if (m.room) noteRoom(m.room, m.slot);
  else if (typeof m.slot === 'number') noteRoom(null, m.slot);
  if (m.picks) {
    picks = {};
    if (val(m.picks, 0)) picks[0] = val(m.picks, 0);
    if (val(m.picks, 1)) picks[1] = val(m.picks, 1);
  }
  if (m.ready) {
    serverReady = { 0: !!val(m.ready, 0), 1: !!val(m.ready, 1) };
  }
  if (m.occupied) {
    occupied = { 0: !!val(m.occupied, 0), 1: !!val(m.occupied, 1) };
  }
  if ((slot === 0 || slot === 1) && picks[slot] && !myPick) {
    myPick = picks[slot];
    highlightPick();
  }
  updateVS();
  syncReadyButton();
  return true;
}

function fightersThumbs() {
  chargrid.innerHTML = '';
  for (const f of FIGHTERS) {
    const d = document.createElement('div');
    d.className = 'char';
    d.dataset.char = f;
    const img = document.createElement('img');
    img.src = `./assets_hd/select/portrait_${f}.png`;
    img.alt = f;
    img.onerror = () => { img.style.display = 'none'; };
    const b = document.createElement('b');
    b.textContent = FNAME[f];
    const s = document.createElement('span');
    s.textContent = 'Tap to pick';
    d.append(img, b, s);
    d.addEventListener('click', () => {
      for (const c of chargrid.children) c.classList.remove('sel');
      d.classList.add('sel');
      myPick = f;
      syncReadyButton();
      if (room && (slot === 0 || slot === 1) && !serverReady[slot]) {
        pickInfo.textContent = `You: ${FNAME[f]} — hit Ready`;
      }
      send({ t: 'pick', char: f, userId });
    });
    chargrid.appendChild(d);
  }
}
fightersThumbs();

function loadImage(img) {
  return new Promise((resolve) => {
    if (img.complete && img.naturalWidth) return resolve();
    const done = () => resolve();
    img.addEventListener('load', done, { once: true });
    img.addEventListener('error', done, { once: true });
  });
}

function loadFighterSheets(char) {
  const info = META ? META.characters[char] : null;
  const states = info ? Object.keys(info) : ['idle', 'walk', 'crouch', 'jump', 'lp', 'hp', 'lk', 'hk', 'block', 'throw', 'hit', 'special1', 'special2', 'super', 'win', 'lose'];
  if (!fighterImgs[char]) fighterImgs[char] = {};
  const jobs = [];
  for (const s of states) {
    if (fighterImgs[char][s] && fighterImgs[char][s].img) {
      jobs.push(loadImage(fighterImgs[char][s].img));
      continue;
    }
    const entry = info ? info[s] : null;
    const file = entry ? entry[0] : `sprites/${char}_${s}.png`;
    const count = entry ? entry[1] : 5;
    const img = new Image();
    fighterImgs[char][s] = { img, count, w: 0, h: 0, fw: 192, frames: count };
    img.onload = () => {
      fighterImgs[char][s].w = img.width;
      fighterImgs[char][s].h = img.height;
      fighterImgs[char][s].fw = Math.floor(img.width / count) || 192;
    };
    img.src = `./assets_hd/${file}`;
    jobs.push(loadImage(img));
  }
  return Promise.all(jobs);
}

function loadStage(name) {
  const base = `./assets_hd/stages/stage_${name}`;
  bgImg = new Image(); bgImg.src = `${base}_bg.png`;
  midImg = new Image(); midImg.src = `${base}_mid.png`;
  fgImg = new Image(); fgImg.src = `${base}_fg.png`;
  return Promise.all([loadImage(bgImg), loadImage(midImg), loadImage(fgImg)]);
}

async function preloadMatch(picksMap, seed) {
  const a = val(picksMap, 0);
  const b = val(picksMap, 1);
  const jobs = [];
  if (a) jobs.push(loadFighterSheets(a));
  if (b) jobs.push(loadFighterSheets(b));
  const stage = STAGES[(Number(seed) || 0) % STAGES.length];
  jobs.push(loadStage(stage));
  await Promise.race([Promise.all(jobs), sleep(8000)]);
  return stage;
}

function onCountdown(m) {
  if (!applySnapshot(m)) return;
  if (!m.startId) return;
  statusEl.textContent = 'Both ready — loading fighters…';
  const startId = m.startId;
  if (loadedFor === startId) {
    transmit({ t: 'loaded', startId });
    return;
  }
  loadedFor = startId;
  preloadMatch(m.picks || picks, m.seed).then(() => {
    if (loadedFor !== startId) return;
    if (!ws || ws.readyState !== 1) return;
    const net = netSample();
    transmit({ t: 'loaded', startId, rtt: net.rtt, jitter: net.jitter, samples: net.samples });
    statusEl.textContent = 'Loaded — waiting for the other player…';
  });
}

function netSample() {
  if (!rttSamples.length) return { rtt: undefined, jitter: undefined, samples: 0 };
  const sorted = [...rttSamples].sort((a, b) => a - b);
  return {
    rtt: sorted[Math.floor(sorted.length / 2)],
    jitter: Math.max(0, sorted[sorted.length - 1] - sorted[0]),
    samples: sorted.length,
  };
}

function onMsg(e) {
  let m;
  try { m = JSON.parse(e.data); } catch { return; }
  if (m.t === 'pong') {
    pingMs = Date.now() - m.ts;
    if (pingMs >= 0 && pingMs < 5000) {
      rttSamples.push(pingMs);
      if (rttSamples.length > 8) rttSamples.shift();
    }
    const pingEl = document.getElementById('ping');
    if (pingEl) pingEl.textContent = pingMs + ' ms';
    return;
  }
  if (m.t === 'queued') {
    statusEl.textContent = 'Searching… share the link to invite someone.';
    return;
  }
  if (m.t === 'matched' || m.t === 'created' || m.t === 'joined') {
    if (!applySnapshot(m)) return;
    const label = m.t === 'matched' ? `Matched in ${room} as P${slot + 1}. Pick a fighter.`
      : m.t === 'created' ? `Room ${room} as P${slot + 1}. Share the code.`
      : `Room ${room} as P${slot + 1}.`;
    if (sim && !sim.closed && m.phase === 'playing') {
      selfHoldUntil = 0;
      statusEl.textContent = 'Opponent reconnected.';
      maybeFlushReady();
      return;
    }
    if (m.phase !== 'playing' && beganId) {
      selfHoldUntil = 0;
      if (sim && !sim.closed) {
        endMatch('Back in the lobby — press Ready to rematch.');
        return;
      }
      statusEl.textContent = 'Back in the lobby — press Ready to rematch.';
      show('lobby');
      if (sim) { sim = null; driveMatch = null; }
      if (myPick) pendingPick = myPick;
      syncReadyButton();
      maybeFlushReady();
      return;
    }
    statusEl.textContent = label;
    if (m.rejoin && myPick && m.phase !== 'playing') pendingPick = myPick;
    maybeFlushReady();
    return;
  }
  if (m.t === 'peer') {
    if (typeof m.epoch === 'number' || typeof m.seq === 'number') {
      if (!acceptMeta(m)) return;
    }
    if (typeof m.slot === 'number') occupied[m.slot] = true;
    if (sim && !sim.closed) {
      if (m.rejoin) statusEl.textContent = 'Opponent reconnected.';
      updateRoomInfo();
      return;
    }
    statusEl.textContent = 'Opponent joined. Pick a fighter.';
    updateRoomInfo();
    return;
  }
  if (m.t === 'peer_pick') {
    if (!acceptMeta(m)) return;
    if (typeof m.slot === 'number' && m.char) picks[m.slot] = m.char;
    peerPick = m.char;
    updateVS();
    return;
  }
  if (m.t === 'room_state') {
    if (!applySnapshot(m)) return;
    if (sim && !sim.closed && m.phase === 'playing') {
      maybeFlushReady();
      return;
    }
    if (sim && sim.closed) {
      maybeFlushReady();
      return;
    }
    if (m.phase === 'lobby' && beganId) {
      selfHoldUntil = 0;
      statusEl.textContent = 'Back in the lobby — press Ready to rematch.';
      show('lobby');
      syncReadyButton();
      maybeFlushReady();
      return;
    }
    if (sim && !sim.closed && m.phase === 'lobby') {
      selfHoldUntil = 0;
      endMatch(m.notice || 'Back in the lobby — press Ready to rematch.');
      return;
    }
    const p0 = val(picks, 0);
    const p1 = val(picks, 1);
    statusEl.textContent = m.notice
      ? m.notice
      : `Room ${room || ''} — P1:${p0 || '—'}${serverReady[0] ? ' ✅' : ''} P2:${p1 || '—'}${serverReady[1] ? ' ✅' : ''}`;
    if (m.phase === 'lobby') loadedFor = null;
    maybeFlushReady();
    return;
  }
  if (m.t === 'countdown') { onCountdown(m); return; }
  if (m.t === 'countdown_cancel') {
    if (!acceptMeta(m)) return;
    loadedFor = null;
    if (m.reason === 'load timeout') serverReady = { 0: false, 1: false };
    statusEl.textContent = m.reason === 'load timeout'
      ? 'Loading took too long. Press Ready again.'
      : 'Start cancelled.';
    syncReadyButton();
    return;
  }
  if (m.t === 'go') {
    if (!applySnapshot(m)) return;
    if (!m.startId || beganId === m.startId) return;
    beganId = m.startId;
    pendingReady = false;
    startMatch(m.picks || picks, m.seed, m.delay);
    return;
  }
  if (m.t === 'ready_ack') {
    if (typeof m.epoch === 'number' || typeof m.seq === 'number') {
      if (!acceptMeta(m)) return;
    }
    if (m.ready && (slot === 0 || slot === 1)) serverReady[slot] = true;
    syncReadyButton();
    statusEl.textContent = `You ready ${Object.values(serverReady).filter(Boolean).length}/2 — waiting for opponent`;
    return;
  }
  if (m.t === 'error') {
    if (typeof m.epoch === 'number' && m.epoch > roomEpoch) roomEpoch = m.epoch;
    pendingReady = false;
    if (/not found|full|no room/i.test(m.msg || '')) stopJoin();
    if (/not found|no room/i.test(m.msg || '')) {
      selfHoldUntil = 0;
      room = null;
      slot = -1;
      roompill.textContent = 'no room';
      statusEl.textContent = 'Not in a room. Create or join to play again.';
      if (sim && !sim.closed) endMatch('Not in a room. Create or join to play again.');
      else {
        show('lobby');
        syncReadyButton();
      }
      return;
    }
    if (slot === 0 || slot === 1) serverReady[slot] = false;
    statusEl.textContent = m.msg || 'Error';
    syncReadyButton();
    return;
  }
  if (m.t === 'peer_left') {
    if (!acceptMeta(m)) return;
    serverReady = { 0: false, 1: false };
    if (typeof m.slot === 'number') {
      occupied[m.slot] = false;
      delete picks[m.slot];
    }
    peerPick = null;
    vsLine.style.display = 'none';
    vsLine.textContent = '';
    loadedFor = null;
    statusEl.textContent = m.notice || 'Opponent left';
    updateRoomInfo();
    if (sim && !sim.closed) endMatch(m.notice || 'Opponent left');
    else syncReadyButton();
    return;
  }
  if (m.t === 'peer_hold') {
    if (!sim || sim.closed) return;
    holdUntil = typeof m.until === 'number' ? m.until : Date.now() + 30000;
    const stall = document.getElementById('stall');
    if (stall) stall.textContent = 'Opponent reconnecting... (30 s)';
    sendHoldFrame();
    return;
  }
  if (m.t === 'need_frame') {
    sendHoldFrame();
    return;
  }
  if (m.t === 'peer_back') {
    holdUntil = 0;
    notePeer();
    const stall = document.getElementById('stall');
    if (stall) stall.textContent = '';
    return;
  }
  if (m.t === 'forfeit') {
    holdUntil = 0;
    selfHoldUntil = 0;
    const mine = m.winner === slot;
    endMatch(mine ? 'You win — opponent left' : 'Opponent left');
    return;
  }
  if (m.t === 'match_end') {
    holdUntil = 0;
    selfHoldUntil = 0;
    endMatch(m.notice || 'Connection lost');
    return;
  }
  if (m.t === 'resume') {
    resumeMatch(m);
    return;
  }
  if (m.t === 'hb') return;
  if (m.t === 'nack') onNack(m);
  if (m.t === 'input') onRemoteInput(m);
  if (m.t === 'hash') {
    if (isGameData(m)) notePeer();
    onRemoteHash(m);
  }
}

quickBtn.onclick = () => {
  stopJoin();
  intentionalLeave = false;
  statusEl.textContent = (ws && ws.readyState === 1) ? 'Searching for an opponent…' : linkStatus(false);
  send({ t: 'quick', userId });
};
createBtn.onclick = () => {
  stopJoin();
  intentionalLeave = false;
  roompill.textContent = 'creating…';
  statusEl.textContent = (ws && ws.readyState === 1) ? 'Creating a room…' : linkStatus(false);
  send({ t: 'create', userId, char: myPick });
};
joinBtn.onclick = () => {
  const code = (roomIn.value.trim() || (location.hash || '').slice(1)).toUpperCase();
  if (!code) { statusEl.textContent = 'Enter a room code.'; return; }
  intentionalLeave = false;
  room = null;
  startJoin(code);
};
copyBtn.onclick = async () => {
  const code = room || (location.hash || '').slice(1) || roomIn.value.trim().toUpperCase();
  const link = location.origin + location.pathname + (code ? '#' + code : '');
  try { await navigator.clipboard.writeText(link); statusEl.textContent = 'Link copied.'; }
  catch { statusEl.textContent = link; }
};
readyBtn.onclick = () => {
  if (!myPick) return;
  send({ t: 'ready', ready: true, userId });
};
leaveBtn.onclick = () => {
  intentionalLeave = true;
  stopJoin();
  pendingReady = false;
  if (ws && ws.readyState === 1) transmit({ t: 'leave', userId });
  localStorage.removeItem('hd2_room');
  room = null;
  slot = -1;
  lastRoom = null;
  picks = {};
  serverReady = { 0: false, 1: false };
  occupied = { 0: false, 1: false };
  roompill.textContent = 'no room';
  vsLine.style.display = 'none';
  leaveBtn.style.display = 'none';
  try { history.replaceState(null, '', location.pathname); } catch {}
  statusEl.textContent = 'Left room.';
  endMatch('Left room');
  syncReadyButton();
};

connect();
ensurePing();
setTimeout(() => {
  if (!ws || ws.readyState !== 1) {
    if (!room) statusEl.textContent = linkStatus(!connectFailedFast);
  }
}, 2000);

const bootCode = ((location.hash || '').slice(1) || localStorage.getItem('hd2_room') || '').toUpperCase();
if (bootCode) {
  roomIn.value = bootCode;
  setTimeout(() => { if (!room) startJoin(bootCode); }, 200);
}


function drawFighter(f, context) {
  // Always draw the selected fighter's own sprites. If a state sheet is still loading, fall back to that
  // fighter's idle (never another look-alike); the placeholder only shows before any sheet has loaded.
  const ok = (x) => x && x.img && x.img.complete && x.img.naturalWidth;
  const set = fighterImgs[f.char] || {};
  const sheet = ok(set[f.state]) ? set[f.state] : (ok(set.idle) ? set.idle : null);
  if (!sheet) {
    drawSilhouette(f, context);
    return;
  }
  const scale = window.innerWidth < 900 ? 2.0 : 1.4;
  const fw = sheet.fw || 192;
  const fh = sheet.h || 256;
  const sw = fw * scale;
  const sh = fh * scale;
  const frames = sheet.frames || 5;
  const sx = (f.frame % frames) * fw;
  const flip = f.facing < 0;
  context.save();
  context.shadowColor = 'rgba(0,0,0,0.7)';
  context.shadowBlur = 8;
  if (flip) {
    context.scale(-1, 1);
    context.drawImage(sheet.img, sx, 0, fw, fh, -f.x - sw / 2, f.y - sh + 12, sw, sh);
  } else {
    context.drawImage(sheet.img, sx, 0, fw, fh, f.x - sw / 2, f.y - sh + 12, sw, sh);
  }
  context.restore();
  if (f.super > 0) {
    context.fillStyle = '#222';
    context.fillRect(f.x - 32, f.y - 126, 64, 4);
    context.fillStyle = '#ffd000';
    context.fillRect(f.x - 32, f.y - 126, 64 * f.super / 100, 4);
  }
}

function drawSilhouette(f, context) {
  const color = f.char === 'void' ? '#6ec8ff' : f.char === 'zap' ? '#ffe14a' : '#c8c8d4';
  context.save();
  context.translate(f.x, f.y);
  context.fillStyle = color;
  context.beginPath();
  if (context.roundRect) context.roundRect(-24, -148, 48, 136, 16);
  else context.rect(-24, -148, 48, 136);
  context.fill();
  context.fillStyle = '#111';
  context.font = '700 13px system-ui';
  context.textAlign = 'center';
  context.fillText(FNAME[f.char] || f.char, 0, -156);
  context.restore();
}

function readLocalInput() {
  const inp = neutralInput();
  if (keys.a || keys.arrowleft) inp.left = true;
  if (keys.d || keys.arrowright) inp.right = true;
  if (keys.w || keys.arrowup) { inp.jump = true; inp.up = true; }
  if (keys.s || keys.arrowdown) inp.down = true;
  if (keys.j) inp.lp = true;
  if (keys.k) inp.hp = true;
  if (keys.n) inp.lk = true;
  if (keys.m) inp.hk = true;
  if (keys[' ']) inp.block = true;
  if (keys.l) inp.throw = true;
  if (keys.q) inp.special1 = true;
  if (keys.e) inp.special2 = true;
  if (keys.r) inp.super = true;
  Object.assign(inp, touchInp);
  const gp = navigator.getGamepads ? navigator.getGamepads()[0] : null;
  if (gp) {
    if (gp.axes[0] < -0.3) inp.left = true;
    if (gp.axes[0] > 0.3) inp.right = true;
    if (gp.axes[1] < -0.5) inp.jump = true;
    if (gp.axes[1] > 0.5) inp.down = true;
    if (gp.buttons[0]?.pressed) inp.lp = true;
    if (gp.buttons[1]?.pressed) inp.hp = true;
    if (gp.buttons[2]?.pressed) inp.lk = true;
    if (gp.buttons[3]?.pressed) inp.hk = true;
    if (gp.buttons[4]?.pressed) inp.block = true;
    if (gp.buttons[5]?.pressed) inp.throw = true;
  }
  return inp;
}

function notePeer(msg) {
  if (msg && !isGameData(msg)) return;
  lastPeerRx = Date.now();
}

function queueLocal(frame) {
  if (!sim || sentFrames.has(frame) || frame < 0) return;
  const inp = cloneInput(readLocalInput());
  if (!sim.setInput(slot, frame, inp)) return;
  sentFrames.add(frame);
  localInputs.set(frame, inp);
  inputLog.push({ frame, inp });
  if (inputLog.length > 90) inputLog.splice(0, inputLog.length - 90);
}

function flushInputs() {
  if (!ws || ws.readyState !== 1 || !room) return;
  const encoded = encodeTail(inputLog, peerAck);
  if (!encoded) return;
  lastInputSend = performance.now();
  transmit(Object.assign({ t: 'input', ack: remoteMax }, encoded));
}

function onNack(m) {
  if (!sim || sim.closed) return;
  if (typeof m.from === 'number' && m.from === slot) return;
  const fromFrame = m.fromFrame | 0;
  const toFrame = m.toFrame | 0;
  if (toFrame < fromFrame) return;
  const rows = [];
  for (let f = fromFrame; f <= toFrame && rows.length < 90; f++) {
    const inp = localInputs.get(f);
    if (inp) rows.push({ frame: f, inp });
  }
  const encoded = encodeFrames(rows);
  if (!encoded || !ws || ws.readyState !== 1) return;
  transmit(Object.assign({ t: 'input', ack: remoteMax }, encoded));
}

function onRemoteInput(m) {
  if (!sim || sim.closed) return;
  if (typeof m.epoch === 'number' && m.epoch !== roomEpoch) return;
  if (isGameData(m)) notePeer();
  if (typeof m.ack === 'number') peerAck = Math.max(peerAck, m.ack);
  const from = m.from === 0 || m.from === 1 ? m.from : (slot ^ 1);
  if (from === slot) return;
  let items = decodeInputs(m);
  if (!items.length && m.inp && typeof m.frame === 'number') {
    items = [{ frame: m.frame, inp: m.inp, bits: packInput(m.inp) }];
  }
  const frames = [];
  for (const item of items) {
    if (!item || typeof item.frame !== 'number') continue;
    const inp = item.inp || unpackInput(item.bits || 0);
    sim.setInput(from, item.frame, inp);
    remoteHave.add(item.frame);
    frames.push(item.frame);
    if (item.frame > remoteMax) remoteMax = item.frame;
  }
  const gap = gapBefore(remoteContig, frames);
  remoteContig = absorbContig(remoteContig, remoteHave);
  const now = Date.now();
  if (gap && (gap.from !== lastNackFrom || now - lastNackAt > 80)) {
    lastNackFrom = gap.from;
    lastNackAt = now;
    const toFrame = Math.min(gap.to, gap.from + 40);
    transmit({ t: 'nack', fromFrame: gap.from, toFrame });
  }
}

function sendHoldFrame() {
  if (!sim || sim.closed) return;
  let base = sim.frame;
  const bits = [];
  for (let f = Math.max(0, sim.frame - 90); f < sim.frame + sim.delay + 4; f++) {
    const inp = localInputs.get(f);
    if (!inp) continue;
    if (!bits.length) base = f;
    while (base + bits.length < f) bits.push(0);
    bits.push(packInput(inp));
  }
  transmit({ t: 'hold_frame', frame: sim.frame, hash: sim.hash() >>> 0, base, bits });
}

function onRemoteHash(m) {
  if (!sim || typeof m.frame !== 'number') return;
  if (typeof m.epoch === 'number' && m.epoch !== roomEpoch) return;
  remoteHashes.set(m.frame, m.hash >>> 0);
  const mine = localHashes.get(m.frame);
  if (mine != null && mine !== (m.hash >>> 0)) flagDesync(m.frame, mine, m.hash >>> 0);
}

function publishHash() {
  if (!sim || sim.frame <= 0 || sim.frame % HASH_EVERY !== 0) return;
  if (localHashes.has(sim.frame)) return;
  const hash = sim.hash() >>> 0;
  localHashes.set(sim.frame, hash);
  lastHash = hash;
  if (ws && ws.readyState === 1) transmit({ t: 'hash', frame: sim.frame, hash });
  const theirs = remoteHashes.get(sim.frame);
  if (theirs != null && theirs !== hash) flagDesync(sim.frame, hash, theirs);
  const dbg = document.getElementById('simdebug');
  if (dbg) {
    dbg.dataset.frame = String(sim.frame);
    dbg.dataset.hash = String(hash);
    dbg.dataset['h' + sim.frame] = String(hash);
    dbg.textContent = `frame=${sim.frame} hash=${hash} delay=${sim.delay}`;
  }
}

let desyncEnded = false;
function flagDesync(frame, local, remote) {
  console.warn('desync', { frame, local, remote });
  const el = document.getElementById('desync');
  if (el) {
    el.textContent = `Desync at frame ${frame}. The two games no longer match.`;
    el.classList.add('show');
  }
  if (!desyncEnded) {
    desyncEnded = true;
    setTimeout(() => endMatch('Desync — no contest'), 600);
  }
}

function resultText() {
  if (!sim || !sim.result) return '';
  if (sim.result === 'time') {
    if (sim.fighters[0].hp === sim.fighters[1].hp) return 'Time up!';
  }
  const w = sim.fighters[sim.winner];
  if (!w) return sim.result === 'time' ? 'Time up!' : 'Draw';
  return `${FNAME[w.char] || w.char} WINS!`;
}

function startMatch(picksMap, seed, delay) {
  const a = val(picksMap, 0) || FIGHTERS[0];
  const b = val(picksMap, 1) || FIGHTERS[1];
  const stage = STAGES[(Number(seed) || 0) % STAGES.length];
  loadFighterSheets(a);
  loadFighterSheets(b);
  loadStage(stage);
  const useDelay = delay > 0 ? delay : DEFAULT_DELAY;
  sim = createMatch({
    p0: a,
    p1: b,
    seed,
    delay: useDelay,
    frames: META && META.characters,
  });
  fighters = sim.fighters;
  inputLog = [];
  sentFrames = new Set();
  localInputs = new Map();
  remoteHave = new Set();
  remoteContig = -1;
  peerAck = -1;
  remoteMax = -1;
  lastInputSend = 0;
  lastPeerRx = Date.now();
  lastNackFrom = -1;
  holdUntil = 0;
  selfHoldUntil = 0;
  stepTimes = [];
  localHashes = new Map();
  remoteHashes = new Map();
  lastHash = 0;
  const clock = createPacer(performance.now());
  const desyncEl = document.getElementById('desync');
  if (desyncEl) { desyncEl.textContent = ''; desyncEl.classList.remove('show'); }
  const ko = document.getElementById('koBanner');
  if (ko) { ko.classList.remove('show'); ko.textContent = ''; }
  show('gameScr');
  nameA.textContent = `P1 ${FNAME[a] || a}`;
  nameB.textContent = `P2 ${FNAME[b] || b}`;
  hpA.style.width = '100%';
  hpB.style.width = '100%';
  timerEl.textContent = '99';
  inviteEl.textContent = location.origin + location.pathname + '#' + (room || '');
  statusEl.textContent = `Fight! ${FNAME[a] || a} vs ${FNAME[b] || b} — ${stage.toUpperCase()}`;
  // Both sides commit the same opening frames before either steps.
  const opening = cloneInput(readLocalInput());
  for (let f = 0; f < useDelay; f++) {
    const inp = cloneInput(opening);
    sim.setInput(slot, f, inp);
    sentFrames.add(f);
    localInputs.set(f, inp);
    inputLog.push({ frame: f, inp });
  }
  flushInputs();
  armLoop(clock, ++matchGen);
}

function armLoop(clock, gen) {
  if (raf) cancelAnimationFrame(raf);
  const loop = (now) => {
    if (!sim || sim.closed || matchGen !== gen) return;
    const stall = document.getElementById('stall');
    const wall = Date.now();
    // Keep the fight screen for the whole 30 s, including after the socket
    // opens, until the server resumes the match or says it is over.
    if (selfHoldUntil && wall < selfHoldUntil) {
      const left = Math.max(0, Math.ceil((selfHoldUntil - wall) / 1000));
      if (stall) stall.textContent = `Reconnecting... (${left} s)`;
      render();
      return;
    }
    if (holdUntil && wall < holdUntil) {
      const left = Math.max(0, Math.ceil((holdUntil - wall) / 1000));
      if (stall) stall.textContent = `Opponent reconnecting... (${left} s)`;
      render();
      return;
    }
    if (selfHoldUntil && wall > selfHoldUntil + 2000 && (!ws || ws.readyState !== 1)) {
      selfHoldUntil = 0;
      endMatch('Connection lost');
      return;
    }
    const budget = stepBudget(clock, sim.frame, now);
    let steps = 0;
    while (steps < budget && sim.canStep() && !sim.result) {
      sim.step();
      steps += 1;
      stepTimes.push(wall);
      if (stepTimes.length > 180) stepTimes.shift();
      queueLocal(sim.frame - 1 + sim.delay);
      publishHash();
      if (sim.result) break;
    }
    if (steps > 0 || now - lastInputSend > 120) flushInputs();
    render();
    if (sim.result) {
      endMatch(resultText());
      return;
    }
    // Own socket is down: keep the fight screen for the 30 s hold. Do not
    // bail to the lobby at 9 s while the server is still waiting.
    if (!ws || ws.readyState !== 1) return;
    const level = evalStall(lastPeerRx, wall);
    if (level === 'lost') {
      if (stall) stall.textContent = 'Connection lost';
      transmit({ t: 'give_up' });
      endMatch('Connection lost');
      return;
    }
    if (level === 'slow') {
      if (stall) stall.textContent = stallLabel(level);
      return;
    }
    if (stall) stall.textContent = poorLink(stepTimes, wall) ? 'Poor connection' : '';
  };
  driveMatch = loop;
  const rafLoop = () => {
    if (!driveMatch || matchGen !== gen) return;
    if (document.visibilityState !== 'hidden') driveMatch(performance.now());
    raf = requestAnimationFrame(rafLoop);
  };
  raf = requestAnimationFrame(rafLoop);
}

function resumeMatch(m) {
  if (!m || typeof m.frame !== 'number') return;
  holdUntil = 0;
  selfHoldUntil = 0;
  notePeer();
  const picksMap = m.picks || picks;
  const a = val(picksMap, 0) || FIGHTERS[0];
  const b = val(picksMap, 1) || FIGHTERS[1];
  const useDelay = m.delay > 0 ? m.delay : DEFAULT_DELAY;
  const fresh = createMatch({
    p0: a, p1: b, seed: m.seed, delay: useDelay, frames: META && META.characters,
  });
  const p0 = unpackHist(m.p0);
  const p1 = unpackHist(m.p1);
  const end = Math.max(m.end | 0, m.frame | 0, p0.length, p1.length);
  for (let f = 0; f < end; f++) {
    fresh.setInput(0, f, unpackInput(p0[f] || 0));
    fresh.setInput(1, f, unpackInput(p1[f] || 0));
  }
  while (fresh.frame < m.frame && fresh.canStep() && !fresh.result) fresh.step();
  if (typeof m.hash === 'number' && (fresh.hash() >>> 0) !== (m.hash >>> 0)) {
    flagDesync(fresh.frame, fresh.hash() >>> 0, m.hash >>> 0);
  }
  sim = fresh;
  fighters = sim.fighters;
  inputLog = [];
  sentFrames = new Set();
  localInputs = new Map();
  remoteHave = new Set();
  remoteContig = -1;
  peerAck = -1;
  remoteMax = -1;
  for (let f = 0; f < end; f++) {
    const mine = slot === 0 ? p0[f] : p1[f];
    if (mine == null) continue;
    const inp = unpackInput(mine);
    sentFrames.add(f);
    localInputs.set(f, inp);
    inputLog.push({ frame: f, inp });
  }
  if (inputLog.length > 90) inputLog.splice(0, inputLog.length - 90);
  for (let f = 0; f < end; f++) remoteHave.add(f);
  remoteContig = end - 1;
  lastPeerRx = Date.now();
  show('gameScr');
  const stall = document.getElementById('stall');
  if (stall) stall.textContent = '';
  statusEl.textContent = 'Opponent reconnected.';
  stepTimes = [];
  const clock = createPacer(performance.now());
  const gen = ++matchGen;
  armLoop(clock, gen);
  flushInputs();
}

function endMatch(msg) {
  if (!sim || sim.closed) return;
  sim.closed = true;
  driveMatch = null;
  holdUntil = 0;
  selfHoldUntil = 0;
  if (raf) cancelAnimationFrame(raf);
  raf = null;
  const banner = document.getElementById('koBanner');
  if (banner && msg && msg !== 'Left room') {
    banner.textContent = msg;
    banner.classList.add('show');
  }
  const frozen = sim;
  const wait = msg && msg !== 'Left room' ? 2200 : 400;
  setTimeout(() => {
    if (sim !== frozen) return;
    if (banner) banner.classList.remove('show');
    sim = null;
    fighters = [null, null];
    statusEl.textContent = msg || '';
    show('lobby');
    if (msg && msg.includes('WINS')) {
      vsLine.style.display = 'block';
      vsLine.textContent = msg;
    }
    syncReadyButton();
  }, wait);
}

function render() {
  if (!sim) return;
  const a = sim.fighters[0];
  const b = sim.fighters[1];
  hpA.style.width = a.hp + '%';
  hpB.style.width = b.hp + '%';
  timerEl.textContent = String(sim.timer).padStart(2, '0');
  ctx.clearRect(0, 0, SCREEN_W, SCREEN_H);
  const shake = sim.hitstop > 0 ? 4 : 0;
  if (shake) {
    ctx.save();
    const dir = (sim.frame % 2) ? 1 : -1;
    ctx.translate(dir * shake, 0);
  }
  if (bgImg.complete && bgImg.naturalWidth) ctx.drawImage(bgImg, 0, 0, SCREEN_W, SCREEN_H);
  else { ctx.fillStyle = '#0e1a33'; ctx.fillRect(0, 0, SCREEN_W, SCREEN_H); }
  if (midImg.complete && midImg.naturalWidth) ctx.drawImage(midImg, 0, 0, SCREEN_W, SCREEN_H);
  ctx.fillStyle = '#2a2a2a';
  ctx.fillRect(0, GROUND_Y, SCREEN_W, SCREEN_H - GROUND_Y);
  ctx.fillStyle = '#111';
  ctx.fillRect(0, GROUND_Y, SCREEN_W, 4);
  if (fgImg.complete && fgImg.naturalWidth) ctx.drawImage(fgImg, 0, 0, SCREEN_W, SCREEN_H);
  for (const f of sim.fighters) {
    ctx.fillStyle = 'rgba(0,0,0,0.35)';
    ctx.beginPath();
    ctx.ellipse(f.x, GROUND_Y + 6, 54, 10, 0, 0, Math.PI * 2);
    ctx.fill();
  }
  const ordered = [...sim.fighters].sort((p, q) => p.x - q.x);
  for (const f of ordered) drawFighter(f, ctx);
  for (const h of sim.hits) {
    const flicker = 200 + ((sim.frame * 17 + Math.round(h.x)) % 55);
    ctx.fillStyle = `rgba(255,${flicker},0,${Math.max(0, h.t) / 0.18})`;
    ctx.fillRect(h.x - 8, h.y - 8, 16, 16);
    ctx.fillStyle = '#fff';
    ctx.fillRect(h.x - 4, h.y - 4, 8, 8);
  }
  if (shake) ctx.restore();
  ctx.fillStyle = '#fff';
  ctx.font = '900 14px system-ui';
  if (a.combo > 1) ctx.fillText(`P1 ${a.combo} HIT COMBO!`, 20, 40);
  if (b.combo > 1) ctx.fillText(`P2 ${b.combo} HIT COMBO!`, SCREEN_W - 180, 40);
}


window.addEventListener('keydown', (e) => {
  keys[e.key.toLowerCase()] = true;
  if (e.key === ' ' || e.key === 'ArrowUp' || e.key === 'ArrowDown') e.preventDefault();
});
window.addEventListener('keyup', (e) => { keys[e.key.toLowerCase()] = false; });

const joy = document.getElementById('joy');
const knob = document.getElementById('knob');
let joyCX = 0, joyCY = 0;
function joyPos(e) {
  const t = e.touches ? e.touches[0] : e;
  return { x: t.clientX, y: t.clientY };
}
function updateJoy(p) {
  let dx = p.x - joyCX, dy = p.y - joyCY;
  const r = 46;
  const d = Math.hypot(dx, dy);
  if (d > r) { dx = dx / d * r; dy = dy / d * r; }
  knob.style.transform = `translate(${dx}px,${dy}px)`;
  touchInp.left = dx < -14;
  touchInp.right = dx > 14;
  touchInp.up = dy < -14;
  touchInp.down = dy > 14;
  touchInp.jump = dy < -22;
}
joy.addEventListener('touchstart', (e) => {
  e.preventDefault();
  const p = joyPos(e);
  const r = joy.getBoundingClientRect();
  joyCX = r.left + r.width / 2;
  joyCY = r.top + r.height / 2;
  updateJoy(p);
}, { passive: false });
joy.addEventListener('touchmove', (e) => { e.preventDefault(); updateJoy(joyPos(e)); }, { passive: false });
joy.addEventListener('touchend', (e) => {
  e.preventDefault();
  touchInp.left = touchInp.right = touchInp.up = touchInp.down = touchInp.jump = false;
  knob.style.transform = 'translate(0,0)';
}, { passive: false });

document.querySelectorAll('.pad .b').forEach((b) => {
  const k = b.dataset.k;
  const set = (v) => {
    if (k === 'up') { touchInp.jump = v; touchInp.up = v; }
    else if (k === 'down') touchInp.down = v;
    else if (k === 'left') touchInp.left = v;
    else if (k === 'right') touchInp.right = v;
    else touchInp[k] = v;
  };
  b.addEventListener('touchstart', (e) => { e.preventDefault(); set(true); b.style.background = '#ffd000'; b.style.color = '#111'; }, { passive: false });
  b.addEventListener('touchend', (e) => { e.preventDefault(); set(false); b.style.background = ''; b.style.color = ''; }, { passive: false });
  b.addEventListener('mousedown', () => set(true));
  b.addEventListener('mouseup', () => set(false));
  b.addEventListener('mouseleave', () => set(false));
});

(function ensureTouchControls() {
  const coarse = window.matchMedia && window.matchMedia('(pointer: coarse)').matches;
  const isTouch = coarse || 'ontouchstart' in window;
  if (isTouch) document.body.classList.add('touch-device');
})();

let wasAway = false;
window.addEventListener('pagehide', () => { wasAway = true; });
window.addEventListener('pageshow', () => {
  if (!wasAway) return;
  wasAway = false;
  const code = (lastRoom || localStorage.getItem('hd2_room') || '').toUpperCase();
  if (code && (!ws || ws.readyState !== 1)) startJoin(code);
});
try {
  const clockWorker = new Worker(new URL('./tick-worker.js', import.meta.url));
  clockWorker.onmessage = () => {
    const now = performance.now();
    if (sim && !sim.closed && ws && ws.readyState === 1 && now - lastHb > 400) {
      lastHb = now;
      transmit({ t: 'hb' });
    }
    if (driveMatch) driveMatch(now);
  };
} catch {}

const demoVid = document.querySelector('#lobby video');
const demoNote = demoVid && demoVid.nextElementSibling;
if (demoVid) {
  const supported = demoVid.canPlayType('video/mp4; codecs="avc1.42E01E"') !== '';
  const showDemoFallback = () => {
    demoVid.style.display = 'none';
    if (demoNote) demoNote.textContent = 'Demo clip cannot play in this browser. Create → Share → Pick → Ready → Fight (10s).';
  };
  if (!supported) showDemoFallback();
  demoVid.addEventListener('error', showDemoFallback);
}

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') {
    if (room) {
      lastRoom = room;
      localStorage.setItem('hd2_room', room);
    }
    return;
  }
  const code = room || lastRoom || localStorage.getItem('hd2_room');
  if (code && (!ws || ws.readyState !== 1)) startJoin(String(code).toUpperCase());
});
window.addEventListener('online', () => {
  const code = room || lastRoom;
  if (code) startJoin(String(code).toUpperCase());
});

