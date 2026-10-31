// Arena FC online server in Node: lobby, rooms, resume tokens, host migration and the authoritative match.
// Speaks the protocol v2 wire format that arena-fc/Web/NetClient.gd (and the C# clients) already use, so the
// browser build connects unchanged, and so arena-fc/Tools/net_smoketest.py / net_v2_smoketest.py pass against it.
//
//   const arena = createArenaServer({ quiet: true });
//   httpServer.on('upgrade', (req, socket, head) => arena.upgrade(req, socket, head));
//   arena.health()  -> JSON for /health
//
// Differences from the .NET server (see ARENA_NODE.md): the simulation is the browser edition's 5-a-side
// sim (arena/sim.js), not the C# MatchEngine; there is no peer-host handoff (the server is always the
// authority); snapshots are full each time (20 Hz) with no client rollback data beyond rng/gt/inputs.
'use strict';
const crypto = require('crypto');
const WebSocket = require('ws');
const { Match, DT, TEAM } = require('./sim');

const PROTOCOL = 2;
const MAX_SLOTS = 4;
const CODE_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';

const sha = (s) => crypto.createHash('sha256').update(s).digest();
const newToken = () => crypto.randomBytes(32).toString('base64url');
const cleanName = (s) => String(s || 'Player').replace(/[^\p{L}\p{N} _.\-]/gu, '').trim().slice(0, 16) || 'Player';
const cleanCode = (s) => String(s || '').toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 12);

function parseOrigins(v) {
  return String(v || '').split(',').map((s) => s.trim().toLowerCase()).filter(Boolean);
}

function createArenaServer(opts = {}) {
  const grace = Math.min(3600, Math.max(5, opts.graceSeconds || Number(process.env.ARENA_GRACE_SECONDS) || 180));
  const maxRooms = opts.maxRooms || 200;
  const maxPerIp = opts.maxPerIp || 16;
  const tickHz = opts.tickHz || 60;
  const snapHz = opts.snapHz || 20;
  const allowed = parseOrigins(opts.allowedOrigins !== undefined ? opts.allowedOrigins : process.env.ARENA_ALLOWED_ORIGINS);
  const trustProxy = opts.trustProxy !== undefined ? opts.trustProxy : process.env.TRUST_PROXY === '1';
  const matchOpts = { seed: opts.seed, halfMinutes: opts.halfMinutes || 45, timeSpeed: opts.timeSpeed || 15 };
  const log = opts.quiet ? () => {} : (...a) => console.log('[arena-fc]', ...a);

  const wss = new WebSocket.Server({ noServer: true, maxPayload: 64 * 1024, perMessageDeflate: false });
  const rooms = new Map();
  const perIp = new Map();
  const stats = { migrations: 0, reconnects: 0, matches: 0, rejected: 0 };
  let ticker = null;
  let last = process.hrtime.bigint();
  let acc = 0;

  // ---------------------------------------------------------------- helpers
  const send = (ws, obj) => {
    if (ws && ws.readyState === WebSocket.OPEN && ws.bufferedAmount < 2 * 1024 * 1024) {
      try { ws.send(JSON.stringify(obj)); } catch (_) { /* closing */ }
    }
  };
  const err = (ws, reason) => send(ws, { t: 'error', reason });

  function newCode() {
    for (let n = 0; n < 50; n++) {
      let c = '';
      for (let i = 0; i < 6; i++) c += CODE_CHARS[crypto.randomInt(CODE_CHARS.length)];
      if (!rooms.has(c)) return c;
    }
    return null;
  }

  function lobbyOf(room) {
    const occ = room.slots.filter(Boolean);
    return {
      t: 'lobby', room: room.code, host: room.host, size: TEAM, authority: 0, started: room.started,
      names: occ.map((s) => s.name), slots: occ.map((s) => s.slot), teams: occ.map((s) => s.team),
      pings: occ.map((s) => s.ping), readys: occ.map((s) => s.ready), onlines: occ.map((s) => !!s.ws),
    };
  }
  const broadcast = (room, obj) => { for (const s of room.slots) if (s && s.ws) send(s.ws, obj); };
  const sendLobby = (room) => broadcast(room, lobbyOf(room));

  function welcomeOf(room, s, withToken) {
    const w = {
      t: 'welcome', ver: PROTOCOL, slot: s.slot, team: s.team, room: room.code, host: room.host, size: TEAM,
      grace, authority: 0, started: room.started, name: s.name,
    };
    if (withToken) w.token = s.tokenPlain;
    return w;
  }

  const pingsOf = (room) => { const out = new Array(MAX_SLOTS).fill(0); for (const s of room.slots) if (s) out[s.slot] = s.ping; return out; };

  function snapMsg(room, kind) {
    const snap = room.match.snapshot();
    snap.pings = pingsOf(room);
    snap.t = kind || 'snap';
    return snap;
  }

  function chooseHost(room) {
    const cands = room.slots.filter((s) => s && s.ws);
    return cands.length ? cands[0].slot : -1;
  }

  function dropRoom(room) {
    rooms.delete(room.code);
    log('room closed', room.code);
  }

  function leaveSlot(room, s, reason) {
    room.slots[s.slot] = null;
    if (room.match) room.match.removeHuman(s.slot);
    if (room.host === s.slot) {
      const prev = s.slot;
      room.host = chooseHost(room);
      if (room.host >= 0) {
        stats.migrations++;
        broadcast(room, { t: 'host', host: room.host, slot: prev, reason: reason || `Host left. Slot ${room.host} is the new host.`, authority: 0, tick: room.match ? room.match.tick : 0, started: room.started });
      }
    }
    if (!room.slots.some(Boolean)) { dropRoom(room); return; }
    sendLobby(room);
  }

  function onDisconnect(room, s) {
    s.ws = null;
    if (!room.started) { leaveSlot(room, s); return; }
    // match running: reserve the slot, AI keeps the player moving
    s.reservedUntil = Date.now() + grace * 1000;
    if (room.host === s.slot) {
      const prev = s.slot;
      const nh = chooseHost(room);
      if (nh >= 0) {
        room.host = nh;
        stats.migrations++;
        broadcast(room, { t: 'host', host: nh, slot: prev, reason: `Host disconnected. Slot ${nh} is the new host.`, authority: 0, tick: room.match.tick, started: true });
      }
    }
    if (!room.slots.some((q) => q && q.ws)) room.emptySince = Date.now();
    sendLobby(room);
  }

  // ---------------------------------------------------------------- message handling
  function handleHello(ws, p) {
    const ver = Number(p.ver) || 1;
    if (ver < 1 || ver > PROTOCOL) { err(ws, `Protocol mismatch: server speaks v${PROTOCOL}.`); return; }
    const name = cleanName(p.name);
    const code = cleanCode(p.room);
    const token = typeof p.token === 'string' ? p.token : '';
    // --- resume with token ---
    if (token.length >= 32 && code) {
      const room = rooms.get(code);
      const h = sha(token);
      const s = room && room.slots.find((q) => q && q.tokenHash && crypto.timingSafeEqual(q.tokenHash, h));
      if (s) {
        if (s.ws && s.ws !== ws) { const old = s.ws; s.ws = null; old.session = null; try { old.close(4000, 'Replaced by reconnect'); } catch (_) { /* gone */ } }
        s.ws = ws; ws.session = { room, slot: s };
        s.reservedUntil = 0; room.emptySince = 0; s.ping = 0;
        stats.reconnects++;
        send(ws, welcomeOf(room, s, false));
        if (room.started) {
          const full = room.match.fullState();
          send(ws, Object.assign(snapMsg(room, 'resume'), { full, inputs: room.match.inputLog.slice(-8) }));
        }
        sendLobby(room);
        log('resume', code, 'slot', s.slot);
        return;
      }
      // an unknown/forged token falls through and is treated as a fresh join (never steals a slot)
    }
    let room = code ? rooms.get(code) : null;
    if (!room) {
      if (code && !p.create) { err(ws, `Room ${code} not found. Ask the host for the code, or create a match.`); return; }
      if (rooms.size >= maxRooms) { err(ws, 'Server is full. Try again later.'); return; }
      const rc = code && code.length >= 3 ? code : newCode();
      if (!rc) { err(ws, 'Could not allocate a room.'); return; }
      room = { code: rc, slots: new Array(MAX_SLOTS).fill(null), host: -1, started: false, match: null, emptySince: 0, created: Date.now() };
      rooms.set(rc, room);
    } else if (p.create) { err(ws, `Room ${code} already exists.`); return; }
    if (room.started) { err(ws, 'That match is already in progress. Rejoin with your saved token, or ask the host for a rematch.'); return; }
    const slot = room.slots.findIndex((q) => !q);
    if (slot < 0) { err(ws, 'Room is full (4 players).'); return; }
    const tokenPlain = newToken();
    const s = { slot, team: slot % 2, name, ready: false, ws, ping: 0, tokenHash: sha(tokenPlain), tokenPlain, reservedUntil: 0, winStart: 0, winCount: 0 };
    room.slots[slot] = s;
    ws.session = { room, slot: s };
    if (room.host < 0) room.host = slot;
    send(ws, welcomeOf(room, s, true));
    s.tokenPlain = '';                       // keep only the hash server-side
    sendLobby(room);
    log('join', room.code, 'slot', slot, name);
  }

  function startMatch(room) {
    const humans = room.slots.filter(Boolean);
    room.match = new Match(Object.assign({}, matchOpts, { seed: matchOpts.seed === undefined ? crypto.randomInt(1, 2 ** 31) : matchOpts.seed }));
    for (const s of humans) room.match.addHuman(s.slot, s.team);
    room.started = true;
    stats.matches++;
    for (const s of room.slots) if (s) s.ready = false;
    broadcast(room, { t: 'begin', room: room.code, size: TEAM, seed: 0, tick: 0 });
    sendLobby(room);
    log('start', room.code, humans.length, 'humans');
  }

  function endMatch(room) {
    const m = room.match;
    const com = `Full time. HAR ${m.score[0]} - ${m.score[1]} NOR`;
    broadcast(room, { t: 'end', com, score: m.score.slice() });
    room.started = false;
    room.match = null;
    // drop reservations from the match; back to the lobby
    for (const s of room.slots.slice()) if (s && !s.ws) leaveSlot(room, s);
    if (rooms.has(room.code)) sendLobby(room);
  }

  function onMessage(ws, raw, isBinary) {
    if (isBinary) return;
    let p;
    try { p = JSON.parse(raw.toString()); } catch (_) { return; }
    if (!p || typeof p !== 'object') return;
    const sess = ws.session;
    if (p.t === 'hello') {
      if (sess) return;
      handleHello(ws, p);
      return;
    }
    if (!sess) return;
    const { room, slot: s } = sess;
    switch (p.t) {
      case 'input': {
        if (!room.started || !room.match) return;
        const now = Date.now();
        if (now - s.winStart > 1000) { s.winStart = now; s.winCount = 0; }
        if (++s.winCount > 150) return;     // flood guard (clients send ~30/s plus one-shots)
        room.match.setInput(s.slot, p.cmd);
        return;
      }
      case 'ready': s.ready = !!p.ready; sendLobby(room); return;
      case 'start':
        if (s.slot !== room.host) { err(ws, 'Only the host can start the match.'); return; }
        if (room.started) return;
        startMatch(room);
        return;
      case 'pong': {
        const ms = Number(p.ms);
        if (Number.isFinite(ms) && ms > 0) s.ping = Math.max(0, Math.min(2000, Math.round(Date.now() - ms)));
        return;
      }
      case 'chat': {
        const m = String(p.m || '').slice(0, 200);
        if (m) broadcast(room, { t: 'chat', name: s.name, slot: s.slot, m });
        return;
      }
      case 'kick': {
        if (s.slot !== room.host) { err(ws, 'Only the host can remove players.'); return; }
        const k = Number(p.kickSlot);
        const target = room.slots[k];
        if (!target || k === s.slot) return;
        if (target.ws) { err(target.ws, 'You were removed by the host.'); const w = target.ws; target.ws = null; w.session = null; try { w.close(4001, 'Kicked'); } catch (_) { /* gone */ } }
        leaveSlot(room, target, `${target.name} was removed.`);
        return;
      }
      case 'leave': try { ws.close(1000, 'bye'); } catch (_) { /* gone */ } return;
      default:
    }
  }

  // ---------------------------------------------------------------- connections
  function clientIp(req) {
    if (trustProxy) {
      const x = String(req.headers['x-forwarded-for'] || '').split(',')[0].trim();
      if (x) return x;
    }
    return (req.socket && req.socket.remoteAddress) || 'unknown';
  }

  function upgrade(req, socket, head) {
    const origin = String(req.headers.origin || '').toLowerCase();
    if (allowed.length && origin && !allowed.includes(origin)) { stats.rejected++; socket.write('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n'); socket.destroy(); return; }
    const ip = clientIp(req);
    if ((perIp.get(ip) || 0) >= maxPerIp) { stats.rejected++; socket.write('HTTP/1.1 429 Too Many Requests\r\nConnection: close\r\n\r\n'); socket.destroy(); return; }
    wss.handleUpgrade(req, socket, head, (ws) => { ws.ip = ip; wss.emit('connection', ws, req); });
  }

  wss.on('connection', (ws) => {
    perIp.set(ws.ip, (perIp.get(ws.ip) || 0) + 1);
    ws.isAlive = true; ws.missed = 0;
    ws.on('pong', () => { ws.isAlive = true; });
    ws.on('message', (d, bin) => { ws.isAlive = true; onMessage(ws, d, bin); });
    ws.on('close', () => {
      perIp.set(ws.ip, Math.max(0, (perIp.get(ws.ip) || 1) - 1));
      const sess = ws.session;
      ws.session = null;
      if (sess && sess.slot.ws === ws) onDisconnect(sess.room, sess.slot);
    });
    ws.on('error', () => { /* close follows */ });
    // first hello must arrive quickly
    ws.helloTimer = setTimeout(() => { if (!ws.session) { try { ws.close(4002, 'hello timeout'); } catch (_) { /* gone */ } } }, 10000);
    if (ws.helloTimer.unref) ws.helloTimer.unref();
  });

  // ---------------------------------------------------------------- clock
  let snapAcc = 0;
  let pingAcc = 0;
  let houseAcc = 0;
  function frame() {
    const now = process.hrtime.bigint();
    const dt = Number(now - last) / 1e9;
    last = now;
    acc += Math.min(dt, 0.25);
    const step = 1 / tickHz;
    let n = 0;
    while (acc >= step && n < 8) {
      acc -= step; n++;
      snapAcc += step; pingAcc += step; houseAcc += step;
      for (const room of rooms.values()) {
        if (!room.started || !room.match) continue;
        room.match.step(DT);
        if (room.match.finished) { endMatch(room); continue; }
      }
      if (snapAcc >= 1 / snapHz) {
        snapAcc = 0;
        for (const room of rooms.values()) if (room.started && room.match) broadcast(room, snapMsg(room));
      }
      if (pingAcc >= 2) {
        pingAcc = 0;
        for (const room of rooms.values()) broadcast(room, { t: 'ping', ms: Date.now() });
        for (const ws of wss.clients) {
          // tolerate ~12 s of silence (6 missed pings): mobile tabs and test clients stall briefly
          if (ws.isAlive) ws.missed = 0; else ws.missed = (ws.missed || 0) + 1;
          if (ws.missed >= 6) { ws.terminate(); continue; }
          ws.isAlive = false;
          try { ws.ping(); } catch (_) { /* closing */ }
        }
      }
      if (houseAcc >= 1) { houseAcc = 0; housekeeping(); }
    }
  }

  function housekeeping() {
    const now = Date.now();
    for (const room of [...rooms.values()]) {
      for (const s of room.slots.slice()) {
        if (s && !s.ws && s.reservedUntil && now > s.reservedUntil) leaveSlot(room, s, `${s.name} did not return in time.`);
      }
      if (!rooms.has(room.code)) continue;
      if (!room.slots.some((q) => q && q.ws)) {
        if (!room.emptySince) room.emptySince = now;
        if (now - room.emptySince > grace * 1000) dropRoom(room);
      }
    }
  }

  ticker = setInterval(frame, Math.round(1000 / tickHz / 2));
  if (ticker.unref) ticker.unref();

  // ---------------------------------------------------------------- admin
  function health() {
    const matches = [];
    let players = 0;
    for (const r of rooms.values()) {
      const online = r.slots.filter((s) => s && s.ws).length;
      players += online;
      matches.push({ room: r.code, online, reserved: r.slots.filter((s) => s && !s.ws).length, host: r.host, authority: 0, started: r.started, tick: r.match ? r.match.tick : 0, score: r.match ? r.match.score.slice() : [0, 0] });
    }
    return { ok: true, game: 'arena-fc', server: 'node', protocol: PROTOCOL, rooms: rooms.size, players, peerHost: false, reconnectGraceSeconds: grace, migrations: stats.migrations, reconnects: stats.reconnects, submits: 0, matchesPlayed: stats.matches, rejected: stats.rejected, matches };
  }

  async function close() {
    if (ticker) clearInterval(ticker);
    for (const ws of wss.clients) { try { ws.terminate(); } catch (_) { /* gone */ } }
    await new Promise((r) => wss.close(() => r()));
  }

  return { wss, upgrade, health, close, rooms, stats, stepOnce: frame };
}

module.exports = { createArenaServer };
