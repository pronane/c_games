const express = require('express');
const http = require('http');
const WebSocket = require('ws');
const path = require('path');

const app = express();
const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

const PORT = process.env.PORT || 3000;
const userRoom = new Map();
function getUserId(ws,m){return (m&&m.userId)||ws.userId||ws.id;}
app.use(express.static(path.join(__dirname, 'public'), { maxAge: 0, etag: false }));
app.use((req,res,next)=>{res.set('Cache-Control','no-store'); next();});
app.use('/assets', express.static(path.join(__dirname, '..', 'assets_hd')));

// Rooms sophisticated: { id, players:[ws0,ws1], userIds:{0:uid,1:uid}, picks:{0:char,1:char}, ready:{0:bool,1:bool}, created, started }
const rooms = new Map();
let nextRoom = 1;
let waiting = null;

function roomId() { return 'R' + String(nextRoom++).padStart(4,'0'); }
function broadcast(room, msg, except=null) {
  for (const p of room.players) if (p && p !== except && p.readyState === WebSocket.OPEN) p.send(JSON.stringify(msg));
}
function saveRoomState(room){ /* placeholder for Redis - in-memory is cache */ }

setInterval(()=>{ wss.clients.forEach(ws=>{ if(ws.isAlive===false) return ws.terminate(); ws.isAlive=false; try{ws.ping()}catch{} }); }, 30000);
wss.on('connection', ws => {
  ws.id = Math.random().toString(36).slice(2,7);
  ws.userId = null;
  ws.room = null;
  ws.slot = -1;
  console.log('connect', ws.id);

  ws.isAlive=true;
  ws.on('pong', ()=>{ ws.isAlive=true; });
  ws.on('message', raw => {
    let m; try { m = JSON.parse(raw); } catch { return; }

    // PING
    if (m.t === 'ping') { ws.send(JSON.stringify({ t: 'pong', ts: m.ts })); return; }

    // QUICK PLAY - auto matchmake with userId
    if (m.t === 'quick') {
      const uid=getUserId(ws,m); ws.userId=uid;
      if (waiting && waiting !== ws && !waiting.room) {
        const id = roomId();
        const room = { id, players: [waiting, ws], userIds:{0:waiting.userId,1:uid}, picks: {}, ready: {}, created: Date.now(), started:false };
        rooms.set(id, room);
        if(waiting.userId) userRoom.set(waiting.userId,id); if(uid) userRoom.set(uid,id);
        waiting.room = room; waiting.slot = 0;
        ws.room = room; ws.slot = 1;
        const a = waiting; waiting = null;
        a.send(JSON.stringify({ t: 'matched', room: id, slot: 0, peer: ws.id, userId:uid }));
        ws.send(JSON.stringify({ t: 'matched', room: id, slot: 1, peer: a.id, userId:a.userId }));
        console.log('matched', id, uid);
      } else {
        waiting = ws;
        ws.send(JSON.stringify({ t: 'queued' }));
      }
      return;
    }

    // CREATE room - userId-backed, cached
    if (m.t === 'create') {
      const uid = getUserId(ws,m); ws.userId = uid;
      if (ws.room) { try{leave(ws)}catch{} }
      // reuse existing room if same user already has one with 1 player and not started
      let existing = userRoom.get(uid);
      if (existing && rooms.has(existing)) {
        const er = rooms.get(existing);
        if (er.players.length===1 && !er.started) { ws.room=er; ws.slot=0; ws.send(JSON.stringify({ t:'created', room:er.id, slot:0, picks:er.picks, rejoin:true })); return; }
      }
      const id = roomId();
      const room = { id, players: [ws], userIds:{0:uid}, picks: {}, ready: {}, created: Date.now(), started:false };
      if (m.char) room.picks[0]=m.char;
      rooms.set(id, room);
      userRoom.set(uid,id);
      ws.room = room; ws.slot = 0;
      ws.send(JSON.stringify({ t: 'created', room: id, slot: 0, picks:room.picks }));
      saveRoomState(room);
      return;
    }

    // JOIN room - leave old, sync cached state, allow rejoin
    if (m.t === 'join') {
      const uid = getUserId(ws,m); ws.userId = uid;
      if (ws.room && ws.room.id === m.room) return ws.send(JSON.stringify({ t: 'joined', room: ws.room.id, slot: ws.slot, picks:ws.room.picks, ready:ws.room.ready }));
      // check if this user already in this room (refresh/rejoin)
      const existingRoom = rooms.get(m.room);
      if (existingRoom) {
        for(let s=0;s<2;s++){ if(existingRoom.userIds[s]===uid){ ws.room=existingRoom; ws.slot=s; // reattach ws
            existingRoom.players[s]=ws;
            ws.send(JSON.stringify({ t:'joined', room:existingRoom.id, slot:s, picks:existingRoom.picks, ready:existingRoom.ready, rejoin:true }));
            broadcast(existingRoom,{t:'peer_rejoin', slot:s, userId:uid},ws);
            return;}}
      }
      if (ws.room) { try{leave(ws)}catch{} }
      const room = rooms.get(m.room);
      if (!room) return ws.send(JSON.stringify({ t: 'error', msg: 'Room not found - try Create new room' }));
      if (room.players.length >= 2 && !room.userIds[0]===uid && !room.userIds[1]===uid) return ws.send(JSON.stringify({ t: 'error', msg: 'Room full (2/2) - Create new room' }));
      if (room.players.length >= 2) { // maybe one slot empty due to disconnect, fill it
        let slot = room.players[0] ? 1 : 0;
        if (room.players.length===2) return ws.send(JSON.stringify({ t: 'error', msg: 'Room full (2/2) - Create new room' }));
      }
      // find empty slot
      let slot = 0; if(room.players[0] && !room.players[1]) slot=1; else if(!room.players[0] && room.players[1]) slot=0; else if(room.players.length===0) slot=0; else slot=1;
      room.players[slot]=ws; if(!room.players[0]) room.players[0]=room.players[slot]; // ensure 0 exists
      // handle sparse array case: normalize to [ws0,ws1]
      if(room.players.length===1 && slot===1){ room.players[1]=ws; } else if(room.players[0]!==ws && room.players[1]!==ws){ room.players.push(ws); slot=room.players.length-1; }
      ws.room = room; ws.slot = slot; room.userIds[slot]=uid; userRoom.set(uid, room.id);
      ws.send(JSON.stringify({ t: 'joined', room: room.id, slot: slot, picks:room.picks, ready:room.ready }));
      broadcast(room, { t: 'peer', id: ws.id, slot: slot, picks:room.picks }, ws);
      // send existing picks to joiner so they see opponent's choice
      if(Object.keys(room.picks).length) ws.send(JSON.stringify({ t:'room_state', picks:room.picks, ready:room.ready }));
      saveRoomState(room);
      return;
    }

    // CHARACTER PICK - cached per room per slot
    if (m.t === 'pick') {
      const r = ws.room; if (!r) return ws.send(JSON.stringify({t:'error',msg:'No room - Create first'}));
      const uid=getUserId(ws,m); ws.userId=uid; if(uid) r.userIds[ws.slot]=uid;
      r.picks[ws.slot] = m.char;
      saveRoomState(r);
      ws.send(JSON.stringify({ t: 'pick_ack', char: m.char, slot:ws.slot }));
      broadcast(r, { t: 'peer_pick', slot: ws.slot, char: m.char, picks:r.picks }, ws);
      if (r.picks[0] && r.picks[1]) {
        broadcast(r, { t: 'both_picked', picks: r.picks });
        r.picks[0] && r.picks[1] && ws.send(JSON.stringify({ t:'both_picked', picks:r.picks }));
      }
      return;
    }

    // READY / START - ensure picks cached, prompt if missing
    if (m.t === 'ready') {
      const r = ws.room; if (!r) return ws.send(JSON.stringify({t:'error',msg:'No room'}));
      if (!r.picks[ws.slot]) return ws.send(JSON.stringify({t:'error',msg:'Pick a fighter first - tap a portrait'}));
      if (!r.picks[ws.slot^1]) {
        ws.send(JSON.stringify({t:'error',msg:'Waiting for opponent to pick...'}));
        broadcast(r,{t:'peer_waiting', slot:ws.slot},ws);
      }
      r.ready[ws.slot] = true;
      saveRoomState(r);
      broadcast(r, { t: 'peer_ready', slot: ws.slot, picks:r.picks, ready:r.ready });
      ws.send(JSON.stringify({t:'ready_ack', slot:ws.slot, ready:r.ready}));
      if (r.ready[0] && r.ready[1]) {
        if (!r.picks[0] || !r.picks[1]) return broadcast(r,{t:'error',msg:'Both must pick fighters first'});
        r.started=true; saveRoomState(r);
        broadcast(r, { t: 'start', picks: r.picks, seed: Date.now() % 10000 });
      } else {
        // send current state to both so UI shows 1/2 ready
        broadcast(r,{t:'room_state', picks:r.picks, ready:r.ready});
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
    broadcast(r, { t: 'peer_left', slot: ws.slot, userId:ws.userId }, ws);
    // keep room+ picks for 60s to allow rejoin, just remove player ref
    r.players[ws.slot]=null; 
    r.players = r.players.filter(Boolean); // compact but keep slot mapping via userIds
    if (r.players.length === 0) {
      // don't delete immediately - keep picks for 2 min for invite link to still work
      setTimeout(()=>{ if(r.players.length===0) { rooms.delete(r.id); console.log('room expired',r.id); } }, 300000);
    }
    ws.room = null;
  }
  if (waiting === ws) waiting = null;
  console.log('leave', ws.id, 'slot',ws.slot, 'user',ws.userId);
}

// Health + room list for lobby
app.get('/api/rooms', (req,res) => {
  res.json([...rooms.values()].map(r => ({ id: r.id, players: r.players.length, picks: r.picks })));
});
app.get('/api/debug', (req,res) => res.json({rooms:[...rooms.keys()], count:rooms.size}));
app.get('/api/health', (req,res) => res.json({ ok: true, rooms: rooms.size }));

server.listen(PORT, '0.0.0.0', () => console.log(`HD Fighter 2 server on http://0.0.0.0:${PORT}`));
