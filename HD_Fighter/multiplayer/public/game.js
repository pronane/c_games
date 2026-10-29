import { createMatch, cloneInput, neutralInput, HASH_EVERY, DEFAULT_DELAY } from './sim.mjs';

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
let inputQueue = [];
let sentFrames = new Set();
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
  if (ws && (ws.readyState === 0 || ws.readyState === 1)) return;
  const sock = new WebSocket(wsURL());
  ws = sock;
  sock.addEventListener('open', () => {
    if (ws !== sock) return;
    setOnline(true);
    flushQueue();
  });
  sock.addEventListener('close', () => {
    if (ws !== sock) return;
    ws = null;
    setOnline(false);
    if (intentionalLeave) return;
    if (joinAttempt) {
      connect();
      return;
    }
    const code = room || lastRoom;
    if (code) {
      setTimeout(() => {
        if (!ws || ws.readyState !== 1) startJoin(String(code).toUpperCase());
      }, 400);
    }
  });
  sock.addEventListener('message', (e) => {
    if (ws !== sock) return;
    onMsg(e);
  });
}

let pingTimer = null;
function ensurePing() {
  if (pingTimer) return;
  pingTimer = setInterval(() => {
    if (ws && ws.readyState === 1) {
      const ts = Date.now();
      ws.send(JSON.stringify({ t: 'ping', ts }));
    }
  }, 2000);
}

function stopJoin() {
  if (!joinAttempt) return;
  if (joinAttempt.timer) clearTimeout(joinAttempt.timer);
  joinAttempt = null;
}

function startJoin(code) {
  code = String(code || '').trim().toUpperCase();
  if (!code) return;
  stopJoin();
  const token = {};
  joinAttempt = { code, token, started: Date.now(), delay: 2000, timer: null, waking: false };
  roomIn.value = code;
  connect();
  const run = (delay) => {
    if (!joinAttempt || joinAttempt.token !== token) return;
    joinAttempt.timer = setTimeout(() => {
      if (!joinAttempt || joinAttempt.token !== token) return;
      if (room === code) { stopJoin(); return; }
      const elapsed = Date.now() - joinAttempt.started;
      if (elapsed > JOIN_GIVE_UP_MS) {
        statusEl.textContent = 'Could not reach the server. It can take about a minute to wake — try again.';
        stopJoin();
        syncReadyButton();
        return;
      }
      const open = ws && ws.readyState === 1;
      if (!open) {
        joinAttempt.waking = true;
        statusEl.textContent = 'Waking the server...';
        connect();
      } else {
        statusEl.textContent = joinAttempt.waking ? `Waking the server... joining ${code}` : `Joining ${code}…`;
        transmit({ t: 'join', room: code, userId });
      }
      const next = joinAttempt.delay;
      joinAttempt.delay = Math.min(10000, Math.round(joinAttempt.delay * 1.5));
      run(next);
    }, delay);
  };
  if (ws && ws.readyState === 1) {
    statusEl.textContent = `Joining ${code}…`;
    transmit({ t: 'join', room: code, userId });
    run(2000);
  } else {
    statusEl.textContent = 'Waking the server...';
    joinAttempt.waking = true;
    run(2000);
  }
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
  if (myPick && p0 && p1) {
    const peer = slot === 1 ? p0 : p1;
    peerPick = peer;
    vsLine.style.display = 'block';
    vsLine.textContent = `VS  ${FNAME[myPick]} (You)  vs  ${FNAME[peer] || peer} — both picked, hit Ready`;
  }
  const s0 = !!val(serverReady, 0);
  const s1 = !!val(serverReady, 1);
  if (s0 && s1) {
    vsLine.style.display = 'block';
    vsLine.textContent = 'Both ready — starting…';
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
    // These three idle sheets are not one fighter per frame (see PR notes).
    const broken = (char === 'brutus' || char === 'void' || char === 'zap') && s === 'idle';
    fighterImgs[char][s] = { img, count, w: 0, h: 0, fw: 192, frames: count, broken };
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
    transmit({ t: 'loaded', startId });
    statusEl.textContent = 'Loaded — waiting for the other player…';
  });
}

function onMsg(e) {
  let m;
  try { m = JSON.parse(e.data); } catch { return; }
  if (m.t === 'pong') {
    pingMs = Date.now() - m.ts;
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
    statusEl.textContent = m.rejoin ? `Rejoined ${room} as P${slot + 1}.` : label;
    if (m.phase === 'playing') {
      statusEl.textContent = 'Rejoined. This match is already underway — press Ready when it ends for a rematch.';
    }
    maybeFlushReady();
    return;
  }
  if (m.t === 'peer') {
    if (typeof m.epoch === 'number' || typeof m.seq === 'number') {
      if (!acceptMeta(m)) return;
    }
    if (typeof m.slot === 'number') occupied[m.slot] = true;
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
    if (/not found|full/i.test(m.msg || '')) stopJoin();
    if (slot === 0 || slot === 1) serverReady[slot] = false;
    statusEl.textContent = m.msg || 'Error';
    syncReadyButton();
    return;
  }
  if (m.t === 'peer_left') {
    if (!acceptMeta(m)) return;
    serverReady = { 0: false, 1: false };
    if (typeof m.slot === 'number') occupied[m.slot] = false;
    loadedFor = null;
    statusEl.textContent = m.notice || 'Opponent left';
    updateRoomInfo();
    if (sim && !sim.closed) endMatch('Opponent left');
    else syncReadyButton();
    return;
  }
  if (m.t === 'input') onRemoteInput(m);
  if (m.t === 'hash') onRemoteHash(m);
}

quickBtn.onclick = () => {
  stopJoin();
  intentionalLeave = false;
  statusEl.textContent = (ws && ws.readyState === 1) ? 'Searching for an opponent…' : 'Waking the server...';
  send({ t: 'quick', userId });
};
createBtn.onclick = () => {
  stopJoin();
  intentionalLeave = false;
  roompill.textContent = 'creating…';
  statusEl.textContent = (ws && ws.readyState === 1) ? 'Creating a room…' : 'Waking the server...';
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
    if (!room) statusEl.textContent = 'Waking the server...';
  }
}, 2000);

const bootCode = ((location.hash || '').slice(1) || localStorage.getItem('hd2_room') || '').toUpperCase();
if (bootCode) {
  roomIn.value = bootCode;
  setTimeout(() => { if (!room) startJoin(bootCode); }, 200);
}

function drawFighter(f, context) {
  const sheet = fighterImgs[f.char]?.[f.state] || fighterImgs[f.char]?.idle;
  const broken = sheet && sheet.broken;
  if (!sheet || !sheet.img.complete || !sheet.img.naturalWidth || broken) {
    drawSilhouette(f, context);
    return;
  }
  const scale = window.innerWidth < 900 ? 1.6 : 1.05;
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
  const color = f.char === 'void' ? '#6ec8ff' : f.char === 'zap' ? '#ffe14a' : '#d7d7e0';
  context.save();
  context.fillStyle = color;
  context.fillRect(f.x - 28, f.y - 132, 56, 120);
  context.beginPath();
  context.arc(f.x, f.y - 148, 18, 0, Math.PI * 2);
  context.fill();
  context.fillStyle = '#fff';
  context.font = '700 14px system-ui';
  context.textAlign = 'center';
  context.fillText(FNAME[f.char] || f.char, f.x, f.y - 176);
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

function queueLocal(frame) {
  if (!sim || sentFrames.has(frame) || frame < 0) return;
  const inp = cloneInput(readLocalInput());
  if (!sim.setInput(slot, frame, inp)) return;
  sentFrames.add(frame);
  inputQueue.push({ frame, inp });
}

function flushInputs() {
  if (!inputQueue.length || !ws || ws.readyState !== 1 || !room) return;
  const batch = inputQueue.splice(0, 30);
  transmit({ t: 'input', batch });
}

function onRemoteInput(m) {
  if (!sim || sim.closed) return;
  if (typeof m.epoch === 'number' && m.epoch !== roomEpoch) return;
  const from = m.from === 0 || m.from === 1 ? m.from : (slot ^ 1);
  if (from === slot) return;
  const items = Array.isArray(m.batch) && m.batch.length
    ? m.batch
    : (typeof m.frame === 'number' ? [{ frame: m.frame, inp: m.inp }] : []);
  for (const item of items) {
    if (!item || typeof item.frame !== 'number') continue;
    sim.setInput(from, item.frame, item.inp);
  }
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

function flagDesync(frame, local, remote) {
  console.warn('desync', { frame, local, remote });
  const el = document.getElementById('desync');
  if (!el) return;
  el.textContent = `Desync at frame ${frame}. The two games no longer match.`;
  el.classList.add('show');
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
  inputQueue = [];
  sentFrames = new Set();
  localHashes = new Map();
  remoteHashes = new Map();
  lastHash = 0;
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
    sim.setInput(slot, f, opening);
    sentFrames.add(f);
    inputQueue.push({ frame: f, inp: cloneInput(opening) });
  }
  flushInputs();
  if (raf) cancelAnimationFrame(raf);
  const gen = ++matchGen;
  const loop = () => {
    if (!sim || sim.closed || matchGen !== gen) return;
    let steps = 0;
    while (sim.canStep() && steps < 8 && !sim.result) {
      sim.step();
      steps += 1;
      queueLocal(sim.frame - 1 + sim.delay);
      publishHash();
      if (sim.result) break;
    }
    flushInputs();
    render();
    if (sim.result) {
      endMatch(resultText());
      return;
    }
    const stall = document.getElementById('stall');
    if (stall) stall.textContent = sim.canStep() ? '' : 'Waiting for opponent…';
    raf = requestAnimationFrame(loop);
  };
  raf = requestAnimationFrame(loop);
}

function endMatch(msg) {
  if (!sim || sim.closed) return;
  sim.closed = true;
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

