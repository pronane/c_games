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
let userId = localStorage.getItem('hd2_userId');
let lastRoom = localStorage.getItem('hd2_room');
if (!userId) {
  userId = 'u' + Math.random().toString(36).slice(2, 9);
  localStorage.setItem('hd2_userId', userId);
}

let myPick = null;
let peerPick = null;
let serverReady = { 0: false, 1: false };
let occupied = { 0: false, 1: false };
let fighters = [null, null];
let match = null;
let keys = {};
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
let raf = null;
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
  if (match && !match.over) return;
  if ((slot === 0 || slot === 1) && serverReady[slot]) {
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
      readyBtn.disabled = false;
      pickInfo.textContent = `You: ${FNAME[f]} — hit Ready`;
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
  const base = `./assets_hd/stages/${name}`;
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
    statusEl.textContent = `Room ${room || ''} — P1:${p0 || '—'}${serverReady[0] ? ' ✅' : ''} P2:${p1 || '—'}${serverReady[1] ? ' ✅' : ''}`;
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
    startMatch(m.picks || picks, m.seed, m.startAt);
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
    if (typeof m.slot === 'number') {
      serverReady[m.slot] = false;
      occupied[m.slot] = false;
    }
    const who = picks[m.slot];
    statusEl.textContent = `P${(m.slot ?? 0) + 1} left${who ? ` (was ${FNAME[who] || who})` : ''}`;
    updateRoomInfo();
    endMatch('Opponent left');
    syncReadyButton();
    return;
  }
  if (m.t === 'input') onRemoteInput(m);
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

class Fighter {
  constructor(idx, char, x, facing) {
    this.idx = idx;
    this.char = char;
    this.x = x;
    this.y = GROUND_Y;
    this.vx = 0;
    this.vy = 0;
    this.facing = facing;
    this.state = 'idle';
    this.frame = 0;
    this.tick = 0;
    this.lock = 0;
    this.hp = 100;
    this.super = 0;
    this.blocking = false;
    this.hitStun = 0;
    this.combo = 0;
  }
  inputToState(inp, other) {
    if (this.hitStun > 0 || this.lock > 0) return;
    if (inp.throw && Math.abs(this.x - other.x) < 70) { this.setState('throw', 18); return; }
    if (inp.lp) { this.setState('lp', 12); return; }
    if (inp.hp) { this.setState('hp', 16); return; }
    if (inp.lk) { this.setState('lk', 12); return; }
    if (inp.hk) { this.setState('hk', 16); return; }
    if (inp.special1) { this.setState('special1', 18); return; }
    if (inp.special2) { this.setState('special2', 18); return; }
    if (inp.super && this.super >= 100) { this.setState('super', 24); this.super = 0; return; }
    if (inp.block) { this.setState('block', 8); this.blocking = true; return; }
    this.blocking = false;
    let mv = 0;
    if (inp.left) mv -= 1;
    if (inp.right) mv += 1;
    if (mv !== 0) {
      this.vx = mv * SPEED;
      if (this.state !== 'walk' && this.y >= GROUND_Y) this.setState('walk');
      this.facing = mv > 0 ? 1 : -1;
    } else {
      this.vx = 0;
      if (this.state === 'walk') this.setState('idle');
    }
    if (inp.jump && this.y >= GROUND_Y) { this.vy = JUMP; this.setState('jump'); }
    if (inp.down && this.y >= GROUND_Y) this.setState('crouch');
  }
  setState(s, lockTicks = 0) {
    if (this.state === s && lockTicks === 0) return;
    this.state = s;
    this.frame = 0;
    this.tick = 0;
    this.lock = lockTicks;
  }
  update(other) {
    if (this.hitStun > 0) this.hitStun -= 1;
    if (this.lock > 0) {
      this.lock -= 1;
      if (this.lock <= 0 && this.state !== 'jump' && this.state !== 'hit') this.setState('idle');
    }
    this.x += this.vx * SIM_DT;
    if (this.y < GROUND_Y || this.vy !== 0) {
      this.y += this.vy * SIM_DT;
      this.vy += GRAV * SIM_DT;
      if (this.y >= GROUND_Y) {
        this.y = GROUND_Y;
        this.vy = 0;
        if (this.state === 'jump') this.setState('idle');
      }
    }
    this.x = Math.max(70, Math.min(SCREEN_W - 70, this.x));
    if (Math.abs(this.x - other.x) > 10) this.facing = other.x > this.x ? 1 : -1;
    this.tick += 1;
    const need = DUR[this.state] || 4;
    if (this.tick >= need) {
      this.tick = 0;
      this.frame += 1;
      const sheet = fighterImgs[this.char]?.[this.state];
      const maxF = sheet ? sheet.frames : 5;
      if (this.frame >= maxF) {
        if (['lp', 'hp', 'lk', 'hk', 'throw', 'special1', 'special2', 'super', 'hit'].includes(this.state)) this.setState('idle');
        else this.frame = 0;
      }
    }
    if (this.state === 'idle' || this.state === 'walk') this.super = Math.min(100, this.super + 0.06);
  }
  hurtbox() { return { x: this.x - 36, y: this.y - 110, w: 72, h: 110 }; }
  hitbox() {
    const s = this.state;
    if (!['lp', 'hp', 'lk', 'hk', 'throw', 'special1', 'special2', 'super'].includes(s)) return null;
    const active = this.frame >= 1 && this.frame <= 2;
    if (!active) return null;
    const dir = this.facing;
    const range = s === 'hp' || s === 'hk' || s === 'super' ? 110 : 78;
    const xoff = dir > 0 ? 20 : -20 - range;
    return { x: this.x + xoff, y: this.y - 95, w: range, h: 34, dmg: DMG[s] || 8 };
  }
  takeHit(dmg, from) {
    if (this.blocking) {
      dmg = Math.floor(dmg * 0.25);
      this.hitStun = 4;
      this.vx = (this.x > from.x ? 1 : -1) * 60;
      return dmg;
    }
    this.hp = Math.max(0, this.hp - dmg);
    this.hitStun = 10;
    this.setState('hit', 10);
    this.vx = (this.x > from.x ? 1 : -1) * 90;
    if (this.hp <= 0) this.setState('lose');
    return dmg;
  }
  draw(context) {
    const sheet = fighterImgs[this.char]?.[this.state] || fighterImgs[this.char]?.idle;
    if (!sheet || !sheet.img.complete) return;
    const scale = window.innerWidth < 900 ? 1.6 : 1.05;
    const fw = sheet.fw || 192;
    const fh = sheet.h || 256;
    const sw = fw * scale;
    const sh = fh * scale;
    const sx = (this.frame % sheet.frames) * fw;
    const flip = this.facing < 0;
    context.save();
    context.shadowColor = 'rgba(0,0,0,0.7)';
    context.shadowBlur = 8;
    if (flip) {
      context.scale(-1, 1);
      context.drawImage(sheet.img, sx, 0, fw, fh, -this.x - sw / 2, this.y - sh + 12, sw, sh);
    } else {
      context.drawImage(sheet.img, sx, 0, fw, fh, this.x - sw / 2, this.y - sh + 12, sw, sh);
    }
    context.restore();
    if (this.super > 0) {
      context.fillStyle = '#222';
      context.fillRect(this.x - 32, this.y - 126, 64, 4);
      context.fillStyle = '#ffd000';
      context.fillRect(this.x - 32, this.y - 126, 64 * this.super / 100, 4);
    }
  }
}

let hitstop = 0;
let shake = 0;
let hits = [];
let touchInp = {};

function currentInputFor(slotIdx) {
  if (slotIdx === slot) return readLocalInput();
  return remoteKeys;
}
function readLocalInput() {
  const inp = { left: false, right: false, up: false, down: false, jump: false, lp: false, hp: false, lk: false, hk: false, block: false, throw: false, special1: false, special2: false, super: false };
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
function sendInput(inp) {
  if (!match || match.over || !ws || ws.readyState !== 1 || !room) return;
  transmit({ t: 'input', inp });
}
function intersect(a, b) {
  return a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
}
function tick(sendNet) {
  if (!match || match.over || !fighters[0] || !fighters[1]) return;
  const myInp = readLocalInput();
  if (sendNet) sendInput(myInp);
  if (hitstop > 0) { hitstop -= 1; return; }
  const inp0 = currentInputFor(0);
  const inp1 = currentInputFor(1);
  fighters[0].inputToState(inp0, fighters[1]);
  fighters[1].inputToState(inp1, fighters[0]);
  fighters[0].update(fighters[1]);
  fighters[1].update(fighters[0]);
  const aHit = fighters[0].hitbox();
  const bHit = fighters[1].hitbox();
  const aHurt = fighters[0].hurtbox();
  const bHurt = fighters[1].hurtbox();
  let hit = false;
  if (aHit && intersect(aHit, bHurt)) {
    fighters[1].takeHit(aHit.dmg, fighters[0]);
    hit = true;
    if (!fighters[1].blocking) fighters[1].combo += 1;
    shake = 6;
    hitstop = 4;
    hits.push({ x: aHit.x + aHit.w / 2, y: aHit.y + 8, t: 0.18 });
  }
  if (bHit && intersect(bHit, aHurt)) {
    fighters[0].takeHit(bHit.dmg, fighters[1]);
    hit = true;
    shake = 6;
    hitstop = 4;
    hits.push({ x: bHit.x + bHit.w / 2, y: bHit.y + 8, t: 0.18 });
  }
  if (hit) {
    hpA.style.width = fighters[0].hp + '%';
    hpB.style.width = fighters[1].hp + '%';
  }
  if (fighters[0].hp <= 0 || fighters[1].hp <= 0) {
    const win = fighters[0].hp > fighters[1].hp ? 0 : 1;
    endMatch(`${FNAME[fighters[win].char]} WINS!`);
    return;
  }
  for (const h of hits) h.t -= SIM_DT;
  hits = hits.filter((h) => h.t > 0);
}

function onRemoteInput(m) {
  if (!m.inp) return;
  if (typeof m.epoch === 'number' && m.epoch !== roomEpoch) return;
  if (m.fromGen != null && m.fromGen !== remoteGen) {
    remoteGen = m.fromGen;
    remoteSeq = -1;
  }
  if (typeof m.seq === 'number') {
    if (m.seq <= remoteSeq) return;
    remoteSeq = m.seq;
  }
  remoteKeys = {
    left: !!m.inp.left, right: !!m.inp.right, up: !!m.inp.up, down: !!m.inp.down,
    jump: !!m.inp.jump, lp: !!m.inp.lp, hp: !!m.inp.hp, lk: !!m.inp.lk, hk: !!m.inp.hk,
    block: !!m.inp.block, throw: !!m.inp.throw, special1: !!m.inp.special1,
    special2: !!m.inp.special2, super: !!m.inp.super,
  };
}

function onSecond() {
  if (!match || match.over) return;
  match.timer = Math.max(0, match.timer - 1);
  timerEl.textContent = String(match.timer).padStart(2, '0');
  if (match.timer <= 0) endMatch('Time up!');
}

function startMatch(picksMap, seed, startAt) {
  const a = val(picksMap, 0) || FIGHTERS[0];
  const b = val(picksMap, 1) || FIGHTERS[1];
  const stage = STAGES[(Number(seed) || 0) % STAGES.length];
  loadFighterSheets(a);
  loadFighterSheets(b);
  loadStage(stage);
  fighters[0] = new Fighter(0, a, 360, 1);
  fighters[1] = new Fighter(1, b, SCREEN_W - 360, -1);
  const gen = ++matchGen;
  const origin = typeof startAt === 'number' ? startAt : Date.now();
  match = { stage, timer: 99, gen, origin, simFrame: 0, over: false };
  hitstop = 0;
  shake = 0;
  hits = [];
  remoteKeys = {};
  show('gameScr');
  nameA.textContent = `P1 ${FNAME[a] || a}`;
  nameB.textContent = `P2 ${FNAME[b] || b}`;
  hpA.style.width = '100%';
  hpB.style.width = '100%';
  timerEl.textContent = '99';
  inviteEl.textContent = location.origin + location.pathname + '#' + (room || '');
  document.getElementById('stage').classList.add('show-touch');
  statusEl.textContent = `Fight! ${FNAME[a] || a} vs ${FNAME[b] || b} — ${stage.toUpperCase()}`;
  if (raf) cancelAnimationFrame(raf);
  const loop = () => {
    if (!match || match.gen !== gen || match.over) return;
    const due = Math.floor((Date.now() - origin) / SIM_MS);
    let steps = 0;
    const behind = due - match.simFrame;
    const cap = behind > 30 ? 10 : Math.max(behind, 0);
    while (match && !match.over && match.simFrame < due && steps < cap) {
      steps += 1;
      const sendNet = behind <= 2 || steps === cap;
      tick(sendNet);
      if (!match || match.over) return;
      match.simFrame += 1;
      if (match.simFrame % SIM_HZ === 0) onSecond();
    }
    render();
    raf = requestAnimationFrame(loop);
  };
  raf = requestAnimationFrame(loop);
}

function endMatch(msg) {
  if (!match || match.over) return;
  match.over = true;
  matchGen += 1;
  if (raf) cancelAnimationFrame(raf);
  raf = null;
  const frozen = match;
  setTimeout(() => {
    if (match === frozen) match = null;
    statusEl.textContent = msg;
    show('lobby');
    if (msg && msg.includes('WINS')) {
      vsLine.style.display = 'block';
      vsLine.textContent = msg;
    }
    syncReadyButton();
  }, 900);
}

function render() {
  if (!match) return;
  ctx.clearRect(0, 0, SCREEN_W, SCREEN_H);
  if (shake > 0) {
    ctx.save();
    ctx.translate((Math.random() - 0.5) * shake * 2, (Math.random() - 0.5) * shake);
    shake = Math.max(0, shake - 0.8);
  }
  if (bgImg.complete && bgImg.naturalWidth) ctx.drawImage(bgImg, 0, 0, SCREEN_W, SCREEN_H);
  else { ctx.fillStyle = '#0e1a33'; ctx.fillRect(0, 0, SCREEN_W, SCREEN_H); }
  if (midImg.complete && midImg.naturalWidth) ctx.drawImage(midImg, 0, 0, SCREEN_W, SCREEN_H);
  ctx.fillStyle = '#2a2a2a';
  ctx.fillRect(0, GROUND_Y, SCREEN_W, SCREEN_H - GROUND_Y);
  ctx.fillStyle = '#111';
  ctx.fillRect(0, GROUND_Y, SCREEN_W, 4);
  if (fgImg.complete && fgImg.naturalWidth) ctx.drawImage(fgImg, 0, 0, SCREEN_W, SCREEN_H);
  for (const f of fighters) {
    if (!f) continue;
    ctx.fillStyle = 'rgba(0,0,0,0.35)';
    ctx.beginPath();
    ctx.ellipse(f.x, GROUND_Y + 6, 54, 10, 0, 0, Math.PI * 2);
    ctx.fill();
  }
  const ordered = fighters.filter(Boolean).sort((a, b) => a.x - b.x);
  for (const f of ordered) f.draw(ctx);
  for (const h of hits) {
    ctx.fillStyle = `rgba(255,${200 + Math.floor(Math.random() * 55)},0,${h.t / 0.18})`;
    ctx.fillRect(h.x - 8, h.y - 8, 16, 16);
    ctx.fillStyle = '#fff';
    ctx.fillRect(h.x - 4, h.y - 4, 8, 8);
  }
  if (shake > 0) ctx.restore();
  ctx.fillStyle = '#fff';
  ctx.font = '900 14px system-ui';
  if (fighters[0] && fighters[0].combo > 1) ctx.fillText(`P1 ${fighters[0].combo} HIT COMBO!`, 20, 40);
  if (fighters[1] && fighters[1].combo > 1) ctx.fillText(`P2 ${fighters[1].combo} HIT COMBO!`, SCREEN_W - 180, 40);
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
  const stage = document.getElementById('stage');
  const isTouch = 'ontouchstart' in window || navigator.maxTouchPoints > 0 || /Mobi|Android|iPhone|iPad|iPod/.test(navigator.userAgent);
  if (isTouch) stage.classList.add('show-touch');
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

const style = document.createElement('style');
style.textContent = '@media(max-width:800px){#stage{margin-bottom:150px}}';
document.head.appendChild(style);
