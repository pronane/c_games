const crypto = require('crypto');
const express = require('express');
const http = require('http');
const path = require('path');
const WebSocket = require('ws');

// Lobby messages are rare. Inputs are a separate bucket: the client steps at
// 60 Hz, so a shared 30-per-10s cap used to close both sockets just after start.
const CTRL_LIMIT = 80;
const CTRL_WINDOW_MS = 10000;
const INPUT_RATE = 240; // one packet per sim frame is 60/s; this stays well above that
const INPUT_BURST = 800;
const INPUT_DROP_CLOSE = 5000; // close only after this many dropped inputs in 10s
const LOAD_TIMEOUT_MS = 20000;
const ROOM_TTL_MS = 300000;
const CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
const FIGHTERS = new Set(['kairo', 'lyra', 'naomi', 'brutus', 'void', 'zap']);
const INPUT_DELAY_FRAMES = 3;

function createServer() {
  const app = express();
  const server = http.createServer(app);
  const wss = new WebSocket.Server({ server });

  const rooms = new Map();
  const userRoom = new Map();
  let waiting = null;
  const intervals = [];
  const timeouts = new Set();

  function noStore(res) {
    res.setHeader('Cache-Control', 'no-store');
  }
  app.use(express.static(path.join(__dirname, 'public'), {
    etag: false,
    maxAge: 0,
    setHeaders: noStore,
  }));
  app.use('/assets', express.static(path.join(__dirname, '..', 'assets_hd'), {
    etag: false,
    maxAge: 0,
    setHeaders: noStore,
  }));

  function later(fn, ms) {
    const t = setTimeout(fn, ms);
    if (t.unref) t.unref();
    timeouts.add(t);
    return t;
  }

  function roomId() {
    for (let attempt = 0; attempt < 32; attempt++) {
      let id = '';
      for (let i = 0; i < 5; i++) id += CODE_ALPHABET[crypto.randomInt(CODE_ALPHABET.length)];
      if (!rooms.has(id)) return id;
    }
    throw new Error('could not allocate a room code');
  }

  function makeRoom(id) {
    return {
      id,
      players: [null, null],
      userIds: { 0: null, 1: null },
      slotGen: { 0: 1, 1: 1 },
      picks: {},
      ready: { 0: false, 1: false },
      readySeq: { 0: -1, 1: -1 },
      loaded: { 0: false, 1: false },
      created: Date.now(),
      started: false,
      phase: 'lobby', // lobby | countdown | playing
      epoch: 1,
      seq: 0,
      seed: null,
      startAt: null,
      startId: null,
      loadTimer: null,
      net: { 0: null, 1: null },
    };
  }

  // Same formula as public/pace.mjs chooseDelay. Both clients are told this
  // number in `go`, so they never pick different delays.
  function chooseDelay(net0, net1) {
    const nets = [net0, net1].filter((n) => n && typeof n.rtt === 'number');
    if (!nets.length) return INPUT_DELAY_FRAMES;
    const rtt = Math.max(...nets.map((n) => n.rtt));
    const jitter = Math.max(...nets.map((n) => Number(n.jitter) || 0));
    const needMs = rtt / 2 + jitter + 30;
    let frames = Math.ceil(needMs / (1000 / 60));
    if (frames < 2) frames = 2;
    if (frames > 8) frames = 8;
    return frames;
  }

  function send(ws, msg) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    try { ws.send(JSON.stringify(msg)); } catch {}
  }

  function broadcast(room, msg, except = null) {
    const data = JSON.stringify(msg);
    for (const p of room.players) {
      if (p && p !== except && p.readyState === WebSocket.OPEN) {
        try { p.send(data); } catch {}
      }
    }
  }

  function snapshot(room) {
    return {
      t: 'room_state',
      room: room.id,
      epoch: room.epoch,
      seq: ++room.seq,
      picks: { 0: room.picks[0] || null, 1: room.picks[1] || null },
      ready: { 0: !!room.ready[0], 1: !!room.ready[1] },
      loaded: { 0: !!room.loaded[0], 1: !!room.loaded[1] },
      occupied: { 0: !!room.players[0], 1: !!room.players[1] },
      phase: room.phase,
      started: !!room.started,
      startId: room.startId,
      seed: room.seed,
      startAt: room.startAt,
    };
  }

  function broadcastState(room) {
    broadcast(room, snapshot(room));
  }

  function countdownMessage(room) {
    return {
      t: 'countdown',
      room: room.id,
      startId: room.startId,
      seed: room.seed,
      startAt: room.startAt,
      picks: { 0: room.picks[0] || null, 1: room.picks[1] || null },
      ready: { 0: !!room.ready[0], 1: !!room.ready[1] },
      occupied: { 0: !!room.players[0], 1: !!room.players[1] },
      phase: room.phase,
      epoch: room.epoch,
      delay: INPUT_DELAY_FRAMES,
      seq: ++room.seq,
    };
  }

  function clearLoadTimer(room) {
    if (room.loadTimer) {
      clearTimeout(room.loadTimer);
      timeouts.delete(room.loadTimer);
      room.loadTimer = null;
    }
  }

  function destroyRoom(room) {
    clearLoadTimer(room);
    rooms.delete(room.id);
    for (const uid of Object.values(room.userIds)) {
      if (uid && userRoom.get(uid) === room.id) userRoom.delete(uid);
    }
    console.log('room expired', room.id);
  }

  function armExpiry(room) {
    later(() => {
      const current = rooms.get(room.id);
      if (current && current.players.filter(Boolean).length === 0) destroyRoom(current);
    }, ROOM_TTL_MS);
  }

  // Detach `old` before closing it so its close handler cannot clear the new socket.
  function placeSocket(room, slot, ws) {
    const old = room.players[slot];
    if (old === ws) {
      ws.room = room;
      ws.slot = slot;
      return;
    }
    if (old) {
      room.slotGen[slot] = (room.slotGen[slot] || 1) + 1;
      old.room = null;
      old.slot = -1;
    }
    room.players[slot] = ws;
    ws.room = room;
    ws.slot = slot;
    if (old && (old.readyState === WebSocket.OPEN || old.readyState === WebSocket.CONNECTING)) {
      try { old.close(4000, 'replaced'); } catch {}
    }
  }

  function slotOf(room, uid) {
    if (room.userIds[0] === uid) return 0;
    if (room.userIds[1] === uid) return 1;
    return -1;
  }

  function otherOccupied(room, uid) {
    for (let s = 0; s < 2; s++) {
      if (room.players[s] && room.userIds[s] !== uid) return true;
    }
    return false;
  }

  function cancelCountdown(room, reason) {
    if (room.phase !== 'countdown') return;
    clearLoadTimer(room);
    room.phase = 'lobby';
    room.started = false;
    room.startId = null;
    room.startAt = null;
    room.seed = null;
    room.loaded = { 0: false, 1: false };
    if (reason === 'load timeout') room.ready = { 0: false, 1: false };
    room.epoch += 1;
    broadcast(room, {
      t: 'countdown_cancel',
      room: room.id,
      reason,
      epoch: room.epoch,
      seq: ++room.seq,
    });
    broadcastState(room);
  }

  function beginCountdown(room) {
    clearLoadTimer(room);
    room.phase = 'countdown';
    room.started = false;
    room.startId = crypto.randomBytes(8).toString('hex');
    room.seed = crypto.randomInt(1, 2147483647);
    room.startAt = Date.now() + 3000;
    room.loaded = { 0: false, 1: false };
    room.epoch += 1;
    const startId = room.startId;
    broadcast(room, countdownMessage(room));
    broadcastState(room);
    room.loadTimer = later(() => {
      if (room.phase === 'countdown' && room.startId === startId) cancelCountdown(room, 'load timeout');
    }, LOAD_TIMEOUT_MS);
    console.log('countdown', room.id, startId);
  }

  function beginGo(room) {
    clearLoadTimer(room);
    room.phase = 'playing';
    room.started = true;
    room.startAt = Math.max(room.startAt || 0, Date.now() + 250);
    room.ready = { 0: false, 1: false };
    room.loaded = { 0: false, 1: false };
    const delay = chooseDelay(room.net && room.net[0], room.net && room.net[1]);
    broadcast(room, {
      t: 'go',
      room: room.id,
      startId: room.startId,
      seed: room.seed,
      startAt: room.startAt,
      picks: { 0: room.picks[0] || null, 1: room.picks[1] || null },
      phase: 'playing',
      started: true,
      delay,
      epoch: room.epoch,
      seq: ++room.seq,
    });
    broadcastState(room);
    console.log('go', room.id, room.startId, 'delay', delay);
  }

  function maybeStart(room) {
    const bothIn = !!(room.players[0] && room.players[1]);
    const bothReady = !!(room.ready[0] && room.ready[1]);
    const bothPicked = !!(room.picks[0] && room.picks[1]);
    if (!bothIn || !bothReady || !bothPicked) {
      if (room.phase === 'countdown') cancelCountdown(room, 'not ready');
      return;
    }
    if (room.phase === 'countdown') return;
    beginCountdown(room);
  }

  function welcome(ws, type, extra) {
    const room = ws.room;
    const snap = snapshot(room);
    send(ws, Object.assign({ t: type, slot: ws.slot }, extra || {}, snap, { t: type, slot: ws.slot }));
    broadcast(room, Object.assign({}, snap, { t: 'room_state' }), ws);
    if (room.phase === 'countdown' && room.startId) send(ws, countdownMessage(room));
  }

  function getUserId(ws, m) {
    const raw = (m && m.userId) || ws.userId || ws.id;
    const id = String(raw || ws.id).slice(0, 64);
    return id || ws.id;
  }

  function registered(ws) {
    const room = ws.room;
    return !!(room && (ws.slot === 0 || ws.slot === 1) && room.players[ws.slot] === ws);
  }

  function takeControl(ws) {
    const now = Date.now();
    if (!ws._cWin || now - ws._cWin > CTRL_WINDOW_MS) {
      ws._cWin = now;
      ws._cCount = 0;
    }
    ws._cCount += 1;
    if (ws._cCount > CTRL_LIMIT) return 'close';
    return 'ok';
  }

  function takeInput(ws) {
    const now = Date.now();
    if (ws._inTokens == null) {
      ws._inTokens = INPUT_BURST;
      ws._inTs = now;
      ws._inDrops = 0;
      ws._inDropTs = now;
    }
    const dt = Math.max(0, now - ws._inTs);
    ws._inTs = now;
    ws._inTokens = Math.min(INPUT_BURST, ws._inTokens + (dt * INPUT_RATE) / 1000);
    if (ws._inTokens >= 1) {
      ws._inTokens -= 1;
      return 'ok';
    }
    if (now - ws._inDropTs > CTRL_WINDOW_MS) {
      ws._inDrops = 0;
      ws._inDropTs = now;
    }
    ws._inDrops += 1;
    if (ws._inDrops >= INPUT_DROP_CLOSE) return 'close';
    return 'drop';
  }

  function leave(ws) {
    if (waiting === ws) waiting = null;
    const room = ws.room;
    if (!room) return;
    const slot = ws.slot;
    // A replaced socket must not evict whoever owns the slot now.
    if ((slot !== 0 && slot !== 1) || room.players[slot] !== ws) {
      ws.room = null;
      ws.slot = -1;
      console.log('leave ignored (stale socket)', ws.id);
      return;
    }
    clearLoadTimer(room);
    const userId = ws.userId;
    room.players[slot] = null;
    // Clear both ready flags. Leaving only the leaver's flag set left the
    // other player stuck on a disabled Ready button through the countdown.
    room.ready = { 0: false, 1: false };
    room.readySeq = { 0: -1, 1: -1 };
    room.loaded = { 0: false, 1: false };
    room.picks[slot] = null;
    // Unconditional: the old check ran after this slot was already cleared, so it never fired.
    room.started = false;
    room.phase = 'lobby';
    room.startId = null;
    room.startAt = null;
    room.seed = null;
    room.epoch += 1;
    ws.room = null;
    ws.slot = -1;
    broadcast(room, {
      t: 'peer_left',
      room: room.id,
      slot,
      userId,
      notice: 'Opponent left',
      ready: { 0: false, 1: false },
      phase: 'lobby',
      started: false,
      epoch: room.epoch,
      seq: ++room.seq,
    });
    broadcast(room, Object.assign(snapshot(room), { notice: 'Opponent left' }));
    if (room.players.filter(Boolean).length === 0) armExpiry(room);
    console.log('leave', ws.id, 'slot', slot, 'user', userId);
  }

  function onMessage(ws, raw) {
    const text = Buffer.isBuffer(raw) ? raw.toString() : String(raw);
    if (text.length > 16384) {
      try { ws.close(1008, 'too big'); } catch {}
      return;
    }
    let m;
    try { m = JSON.parse(text); } catch { return; }
    if (!m || typeof m !== 'object' || typeof m.t !== 'string') return;

    if (m.t === 'input' || m.t === 'hash') {
      const gate = takeInput(ws);
      if (gate === 'close') {
        try { ws.close(1008, 'rate limited'); } catch {}
        return;
      }
      if (gate === 'drop') return;
      const room = ws.room;
      if (!room || room.players[ws.slot] !== ws) return;
      if (m.epoch != null && Number(m.epoch) !== room.epoch) return;
      if (m.t === 'hash') {
        broadcast(room, {
          t: 'hash',
          frame: m.frame,
          hash: m.hash,
          from: ws.slot,
          epoch: room.epoch,
        }, ws);
        return;
      }
      let batch = null;
      if (Array.isArray(m.batch)) {
        batch = [];
        for (const item of m.batch) {
          if (!item || typeof item.frame !== 'number' || item.frame < 0 || item.frame > 1000000) continue;
          batch.push({ frame: item.frame | 0, inp: item.inp || null });
          if (batch.length >= 30) break;
        }
      }
      broadcast(room, {
        t: 'input',
        inp: m.inp,
        n: m.n,
        frame: typeof m.frame === 'number' ? m.frame : null,
        batch,
        ack: typeof m.ack === 'number' ? m.ack : null,
        seq: typeof m.seq === 'number' ? m.seq : null,
        from: ws.slot,
        fromGen: room.slotGen[ws.slot],
        epoch: room.epoch,
        ts: Date.now(),
      }, ws);
      return;
    }

    const gate = takeControl(ws);
    if (gate === 'close') {
      try { ws.close(1008, 'rate limited'); } catch {}
      return;
    }

    if (m.t === 'ping') {
      send(ws, { t: 'pong', ts: m.ts });
      return;
    }

    if (m.t === 'quick') {
      const uid = getUserId(ws, m);
      ws.userId = uid;
      if (ws.room) leave(ws);
      if (waiting && waiting.readyState !== WebSocket.OPEN) waiting = null;
      if (waiting && waiting === ws) {
        send(ws, { t: 'queued' });
        return;
      }
      if (waiting && waiting.userId === uid) {
        const old = waiting;
        waiting = ws;
        try { old.close(4000, 'replaced'); } catch {}
        send(ws, { t: 'queued' });
        return;
      }
      if (waiting && waiting !== ws && !waiting.room) {
        const id = roomId();
        const room = makeRoom(id);
        rooms.set(id, room);
        placeSocket(room, 0, waiting);
        placeSocket(room, 1, ws);
        room.userIds[0] = waiting.userId;
        room.userIds[1] = uid;
        if (waiting.userId) userRoom.set(waiting.userId, id);
        userRoom.set(uid, id);
        const peer = waiting;
        waiting = null;
        welcome(peer, 'matched', { peer: ws.id, userId: uid });
        welcome(ws, 'matched', { peer: peer.id, userId: peer.userId });
        console.log('matched', id);
        return;
      }
      waiting = ws;
      send(ws, { t: 'queued' });
      return;
    }

    if (m.t === 'create') {
      const uid = getUserId(ws, m);
      ws.userId = uid;
      if (ws.room) leave(ws);
      const existingId = userRoom.get(uid);
      if (existingId && rooms.has(existingId)) {
        const existing = rooms.get(existingId);
        const owned = slotOf(existing, uid);
        if (owned !== -1 && !otherOccupied(existing, uid)) {
          placeSocket(existing, owned, ws);
          existing.userIds[owned] = uid;
          userRoom.set(uid, existing.id);
          if (m.char && FIGHTERS.has(m.char)) existing.picks[owned] = m.char;
          welcome(ws, 'created', { rejoin: true });
          console.log('create rejoin', existing.id, 'slot', owned);
          return;
        }
      }
      const id = roomId();
      const room = makeRoom(id);
      rooms.set(id, room);
      placeSocket(room, 0, ws);
      room.userIds[0] = uid;
      userRoom.set(uid, id);
      if (m.char && FIGHTERS.has(m.char)) room.picks[0] = m.char;
      welcome(ws, 'created', { rejoin: false });
      console.log('create', id);
      return;
    }

    if (m.t === 'join') {
      const uid = getUserId(ws, m);
      ws.userId = uid;
      const code = typeof m.room === 'string' ? m.room.trim().toUpperCase() : '';
      const room = rooms.get(code);
      if (!room) {
        send(ws, { t: 'error', msg: 'Room not found' });
        return;
      }
      if (ws.room && ws.room !== room) leave(ws);
      if (ws.room === room && room.players[ws.slot] === ws) {
        welcome(ws, 'joined', { rejoin: true });
        return;
      }
      const owned = slotOf(room, uid);
      if (owned !== -1) {
        placeSocket(room, owned, ws);
        room.userIds[owned] = uid;
        userRoom.set(uid, room.id);
        welcome(ws, 'joined', { rejoin: true });
        broadcast(room, { t: 'peer', id: ws.id, slot: owned, rejoin: true, epoch: room.epoch, seq: ++room.seq }, ws);
        console.log('rejoin', room.id, 'slot', owned);
        return;
      }
      const openSlot = room.players[0] ? (room.players[1] ? -1 : 1) : 0;
      if (openSlot === -1) {
        send(ws, { t: 'error', msg: 'Room full (2/2)' });
        return;
      }
      placeSocket(room, openSlot, ws);
      room.userIds[openSlot] = uid;
      userRoom.set(uid, room.id);
      welcome(ws, 'joined', { rejoin: false });
      broadcast(room, { t: 'peer', id: ws.id, slot: openSlot, epoch: room.epoch, seq: ++room.seq }, ws);
      console.log('join', room.id, 'slot', openSlot);
      return;
    }

    if (m.t === 'pick') {
      if (!registered(ws)) return send(ws, { t: 'error', msg: 'No room' });
      if (!FIGHTERS.has(m.char)) return send(ws, { t: 'error', msg: 'Unknown fighter' });
      const room = ws.room;
      if (m.epoch != null && Number(m.epoch) !== room.epoch) {
        send(ws, { t: 'error', msg: 'Room changed — pick again', stale: true, epoch: room.epoch });
        return;
      }
      room.picks[ws.slot] = m.char;
      send(ws, { t: 'pick_ack', char: m.char, slot: ws.slot, epoch: room.epoch, seq: room.seq });
      broadcast(room, { t: 'peer_pick', slot: ws.slot, char: m.char, epoch: room.epoch, seq: ++room.seq }, ws);
      broadcastState(room);
      maybeStart(room);
      return;
    }

    if (m.t === 'ready') {
      if (!registered(ws)) return send(ws, { t: 'error', msg: 'No room' });
      const room = ws.room;
      if (m.epoch != null && Number(m.epoch) !== room.epoch) {
        send(ws, { t: 'error', msg: 'Room changed — press Ready again', stale: true, epoch: room.epoch });
        return;
      }
      if (typeof m.readySeq === 'number') {
        if (m.readySeq < room.readySeq[ws.slot]) return; // older than one we already applied
        room.readySeq[ws.slot] = m.readySeq;
      }
      if (!room.picks[ws.slot]) return send(ws, { t: 'error', msg: 'Pick a fighter first' });
      // SET, never toggle. Omitted `ready` means true so a plain {t:'ready'} still readies.
      const value = !(m.ready === false || m.ready === 0 || m.ready === 'false');
      room.ready[ws.slot] = value;
      if (!value && room.phase === 'countdown') {
        cancelCountdown(room, 'ready cleared');
        return;
      }
      broadcastState(room);
      send(ws, {
        t: 'ready_ack',
        slot: ws.slot,
        ready: !!room.ready[ws.slot],
        epoch: room.epoch,
        seq: room.seq,
      });
      maybeStart(room);
      return;
    }

    if (m.t === 'loaded') {
      if (!registered(ws)) return;
      const room = ws.room;
      if (room.phase !== 'countdown' || m.startId !== room.startId) return;
      if (m.epoch != null && Number(m.epoch) !== room.epoch) return;
      room.loaded[ws.slot] = true;
      if (typeof m.rtt === 'number') {
        room.net[ws.slot] = {
          rtt: Math.max(0, Math.min(2000, Number(m.rtt))),
          jitter: Math.max(0, Math.min(1000, Number(m.jitter) || 0)),
        };
      }
      broadcastState(room);
      if (room.loaded[0] && room.loaded[1]) beginGo(room);
      return;
    }

    if (m.t === 'state' || m.t === 'hit' || m.t === 'chat') {
      if (!registered(ws)) return;
      m.from = ws.slot;
      m.epoch = ws.room.epoch;
      m.ts = Date.now();
      broadcast(ws.room, m, ws);
      return;
    }

    if (m.t === 'leave') leave(ws);
  }

  wss.on('connection', (ws) => {
    ws.id = crypto.randomBytes(3).toString('hex');
    ws.userId = null;
    ws.room = null;
    ws.slot = -1;
    ws.isAlive = true;
    ws.on('pong', () => { ws.isAlive = true; });
    ws.on('message', (raw) => onMessage(ws, raw));
    ws.on('close', () => leave(ws));
    console.log('connect', ws.id);
  });

  const heartbeat = setInterval(() => {
    wss.clients.forEach((ws) => {
      if (ws.isAlive === false) return ws.terminate();
      ws.isAlive = false;
      try { ws.ping(); } catch {}
    });
  }, 30000);
  if (heartbeat.unref) heartbeat.unref();
  intervals.push(heartbeat);

  app.get('/api/rooms', (req, res) => {
    res.json([...rooms.values()].map((r) => ({
      id: r.id,
      players: r.players.filter(Boolean).length,
      picks: r.picks,
      phase: r.phase,
      started: !!r.started,
    })));
  });
  app.get('/api/health', (req, res) => res.json({ ok: true, rooms: rooms.size, protocol: 2 }));

  function listen(port, host) {
    return new Promise((resolve, reject) => {
      const onError = (err) => reject(err);
      server.once('error', onError);
      server.listen(port, host || '0.0.0.0', () => {
        server.removeListener('error', onError);
        resolve(server.address().port);
      });
    });
  }

  async function close() {
    for (const t of timeouts) clearTimeout(t);
    timeouts.clear();
    for (const i of intervals) clearInterval(i);
    intervals.length = 0;
    for (const room of rooms.values()) clearLoadTimer(room);
    for (const client of wss.clients) {
      try { client.terminate(); } catch {}
    }
    await Promise.race([
      new Promise((resolve) => wss.close(() => resolve())),
      new Promise((resolve) => setTimeout(resolve, 500)),
    ]);
    if (server.listening) {
      await new Promise((resolve) => server.close(() => resolve()));
    }
  }

  return { listen, close, app, server };
}

if (require.main === module) {
  const port = Number(process.env.PORT || 3000);
  const srv = createServer();
  srv.listen(port, '0.0.0.0').then((bound) => {
    console.log(`HD Fighter 2 server on http://0.0.0.0:${bound}`);
  }).catch((err) => {
    console.error(err);
    process.exit(1);
  });
}

module.exports = { createServer };
