const express = require('express');
const http = require('http');
const WebSocket = require('ws');
const path = require('path');

const app = express();
const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

const PORT = process.env.PORT || 3000;
app.use(express.static(path.join(__dirname, 'public'), { maxAge: 0, etag: false }));
app.use((req,res,next)=>{res.set('Cache-Control','no-store'); next();});
app.use('/assets', express.static(path.join(__dirname, '..', 'assets_hd')));

// Rooms: { id: { players: [ws1, ws2], picks: {}, ready: {}, state: {} } }
const rooms = new Map();
let nextRoom = 1;
let waiting = null;

function roomId() { return 'R' + String(nextRoom++).padStart(4,'0'); }
function broadcast(room, msg, except=null) {
  for (const p of room.players) if (p !== except && p.readyState === WebSocket.OPEN) p.send(JSON.stringify(msg));
}

wss.on('connection', ws => {
  ws.id = Math.random().toString(36).slice(2,7);
  ws.room = null;
  ws.slot = -1;
  console.log('connect', ws.id);

  ws.on('message', raw => {
    let m; try { m = JSON.parse(raw); } catch { return; }

    // PING
    if (m.t === 'ping') { ws.send(JSON.stringify({ t: 'pong', ts: m.ts })); return; }

    // QUICK PLAY - auto matchmake
    if (m.t === 'quick') {
      if (waiting && waiting !== ws && !waiting.room) {
        // pair up
        const id = roomId();
        const room = { id, players: [waiting, ws], picks: {}, ready: {}, created: Date.now() };
        rooms.set(id, room);
        waiting.room = room; waiting.slot = 0;
        ws.room = room; ws.slot = 1;
        const a = waiting; waiting = null;
        a.send(JSON.stringify({ t: 'matched', room: id, slot: 0, peer: ws.id }));
        ws.send(JSON.stringify({ t: 'matched', room: id, slot: 1, peer: a.id }));
        console.log('matched', id);
      } else {
        waiting = ws;
        ws.send(JSON.stringify({ t: 'queued' }));
      }
      return;
    }

    // CREATE room - leave old first
    if (m.t === 'create') {
      if (ws.room) { try{leave(ws)}catch{} }
      const id = roomId();
      const room = { id, players: [ws], picks: {}, ready: {}, created: Date.now() };
      rooms.set(id, room);
      ws.room = room; ws.slot = 0;
      ws.send(JSON.stringify({ t: 'created', room: id, slot: 0 }));
      return;
    }

    // JOIN room - leave old first
    if (m.t === 'join') {
      if (ws.room && ws.room.id === m.room) return ws.send(JSON.stringify({ t: 'joined', room: ws.room.id, slot: ws.slot }));
      if (ws.room) { try{leave(ws)}catch{} }
      const room = rooms.get(m.room);
      if (!room) return ws.send(JSON.stringify({ t: 'error', msg: 'Room not found - try Create new room' }));
      if (room.players.length >= 2) return ws.send(JSON.stringify({ t: 'error', msg: 'Room full (2/2) - Create new room' }));
      room.players.push(ws);
      ws.room = room; ws.slot = 1;
      ws.send(JSON.stringify({ t: 'joined', room: room.id, slot: 1 }));
      broadcast(room, { t: 'peer', id: ws.id, slot: 1 }, ws);
      room.players[0].send(JSON.stringify({ t: 'peer', id: ws.id, slot: 1 }));
      return;
    }

    // CHARACTER PICK
    if (m.t === 'pick') {
      const r = ws.room; if (!r) return;
      r.picks[ws.slot] = m.char;
      ws.send(JSON.stringify({ t: 'pick_ack', char: m.char }));
      broadcast(r, { t: 'peer_pick', slot: ws.slot, char: m.char }, ws);
      if (r.picks[0] && r.picks[1]) {
        broadcast(r, { t: 'both_picked', picks: r.picks });
      }
      return;
    }

    // READY / START - ensure picks
    if (m.t === 'ready') {
      const r = ws.room; if (!r) return;
      const F=['kairo','lyra','naomi','brutus','void','zap'];
      if (!r.picks[ws.slot]) r.picks[ws.slot]=F[ws.slot%6];
      r.ready[ws.slot] = true;
      broadcast(r, { t: 'peer_ready', slot: ws.slot });
      if (r.ready[0] && r.ready[1]) {
        if (!r.picks[0]) r.picks[0]='kairo';
        if (!r.picks[1]) r.picks[1]='lyra';
        broadcast(r, { t: 'start', picks: r.picks, seed: Date.now() % 10000 });
      }
      return;
    }

    // INPUT: relay to peer(s) with server tick
    if (m.t === 'input' || m.t === 'state' || m.t === 'hit' || m.t === 'chat') {
      const r = ws.room; if (!r) return;
      m.from = ws.slot;
      m.ts = Date.now();
      broadcast(r, m, ws);
      return;
    }

    // LEAVE
    if (m.t === 'leave') {
      leave(ws); return;
    }
  });

  ws.on('close', () => leave(ws));
});

function leave(ws) {
  const r = ws.room;
  if (r) {
    broadcast(r, { t: 'peer_left', slot: ws.slot }, ws);
    r.players = r.players.filter(p => p !== ws);
    if (r.players.length === 0) rooms.delete(r.id);
    ws.room = null;
  }
  if (waiting === ws) waiting = null;
  console.log('leave', ws.id);
}

// Health + room list for lobby
app.get('/api/rooms', (req,res) => {
  res.json([...rooms.values()].map(r => ({ id: r.id, players: r.players.length, picks: r.picks })));
});
app.get('/api/debug', (req,res) => res.json({rooms:[...rooms.keys()], count:rooms.size}));
app.get('/api/health', (req,res) => res.json({ ok: true, rooms: rooms.size }));

server.listen(PORT, '0.0.0.0', () => console.log(`HD Fighter 2 server on http://0.0.0.0:${PORT}`));
