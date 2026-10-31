// WebSocket reverse proxy for games whose server is NOT the lockstep relay.
//
// Arena FC runs an authoritative .NET server (arena-fc/Server, listening on 127.0.0.1:7777). Browsers
// cannot reach it directly: the page is served over HTTPS, so the socket has to be wss:// on the same
// host. This puts the .NET server behind the same Node process that already serves HD Fighter,
// Egyptian Fighter and TurboTumble64, so one public port, one TLS certificate and one deploy cover all.
//
// It only forwards frames. It does not parse them, so the .NET server's own protocol (lobby, resume
// tokens, host migration) is untouched. What it adds on top:
//   * an Origin allow-list (opts.allowedOrigins or env ARENA_ALLOWED_ORIGINS, comma separated)
//   * a per-IP connection cap and a payload cap (the backend sees one client per browser socket)
//   * keep-alive pings, because hosts such as Render drop idle WebSockets after about a minute
//   * a bounded queue while the backend socket is still opening, and a cap on slow readers
//   * health(): true when the backend port accepts connections
//
//   const p = createWsProxy({ target: 'ws://127.0.0.1:7777' });
//   server.on('upgrade', (req, socket, head) => p.upgrade(req, socket, head));
const net = require('net');
const WebSocket = require('ws');

const BAD_CLOSE_CODES = new Set([1004, 1005, 1006, 1015]);

function closeCode(code) {
  return Number.isInteger(code) && code >= 1000 && code <= 4999 && !BAD_CLOSE_CODES.has(code) ? code : 1000;
}

function parseOrigins(v) {
  if (Array.isArray(v)) return v.map((s) => String(s).trim().toLowerCase()).filter(Boolean);
  return String(v || '').split(',').map((s) => s.trim().toLowerCase()).filter(Boolean);
}

function createWsProxy(opts = {}) {
  const target = new URL(opts.target || process.env.ARENA_BACKEND || 'ws://127.0.0.1:7777');
  const label = opts.label || 'proxy';
  const allowed = parseOrigins(opts.allowedOrigins !== undefined ? opts.allowedOrigins : process.env.ARENA_ALLOWED_ORIGINS);
  const maxPerIp = opts.maxPerIp || 16;
  const maxQueue = opts.maxQueue || 64;
  const maxBuffered = opts.maxBuffered || 4 * 1024 * 1024;
  const pingMs = opts.pingMs === undefined ? 30000 : opts.pingMs;
  const trustProxy = opts.trustProxy !== undefined ? opts.trustProxy : process.env.TRUST_PROXY === '1';
  const log = opts.quiet ? () => {} : (...a) => console.log(`[${label}]`, ...a);

  const wss = new WebSocket.Server({ noServer: true, maxPayload: opts.maxPayload || 1024 * 1024, perMessageDeflate: false });
  const live = new Set();
  const perIp = new Map();
  let accepted = 0;
  let rejected = 0;

  const timer = pingMs > 0 ? setInterval(() => {
    for (const c of live) {
      if (c.isAlive === false) { c.terminate(); continue; }
      c.isAlive = false;
      try { c.ping(); } catch (_) { /* socket already closing */ }
    }
  }, pingMs) : null;
  if (timer && timer.unref) timer.unref();

  function clientIp(req) {
    if (trustProxy) {
      const xff = String(req.headers['x-forwarded-for'] || '').split(',')[0].trim();
      if (xff) return xff;
    }
    return (req.socket && req.socket.remoteAddress) || 'unknown';
  }

  function refuse(socket, status, text) {
    rejected++;
    try {
      socket.write(`HTTP/1.1 ${status} ${text}\r\nConnection: close\r\nContent-Length: 0\r\n\r\n`);
    } catch (_) { /* ignore */ }
    socket.destroy();
  }

  function upgrade(req, socket, head) {
    const origin = String(req.headers.origin || '').toLowerCase();
    if (allowed.length && origin && !allowed.includes(origin)) {
      log('refused origin', origin);
      return refuse(socket, 403, 'Forbidden');
    }
    const ip = clientIp(req);
    if ((perIp.get(ip) || 0) >= maxPerIp) {
      log('refused (too many connections)', ip);
      return refuse(socket, 429, 'Too Many Requests');
    }
    wss.handleUpgrade(req, socket, head, (client) => bridge(client, ip, req));
  }

  function bridge(client, ip, req) {
    accepted++;
    live.add(client);
    perIp.set(ip, (perIp.get(ip) || 0) + 1);
    client.isAlive = true;
    client.on('pong', () => { client.isAlive = true; });

    const headers = { 'X-Forwarded-For': ip };
    if (req.headers['user-agent']) headers['User-Agent'] = req.headers['user-agent'];
    const backend = new WebSocket(target.href, { perMessageDeflate: false, handshakeTimeout: 5000, headers });
    const queue = [];
    let done = false;

    function finish(code, reason) {
      if (done) return;
      done = true;
      live.delete(client);
      const n = (perIp.get(ip) || 1) - 1;
      if (n <= 0) perIp.delete(ip); else perIp.set(ip, n);
      const c = closeCode(code);
      const r = Buffer.isBuffer(reason) ? reason.toString().slice(0, 120) : String(reason || '').slice(0, 120);
      for (const s of [client, backend]) {
        try {
          if (s.readyState === WebSocket.OPEN) s.close(c, r);
          else if (s.readyState === WebSocket.CONNECTING) s.terminate();
        } catch (_) { /* ignore */ }
      }
    }

    client.on('message', (data, isBinary) => {
      if (backend.readyState === WebSocket.OPEN) {
        backend.send(data, { binary: isBinary });
      } else if (backend.readyState === WebSocket.CONNECTING) {
        if (queue.length >= maxQueue) return finish(1013, 'backend busy');
        queue.push([data, isBinary]);
      }
    });
    backend.on('open', () => {
      for (const [d, b] of queue.splice(0)) backend.send(d, { binary: b });
    });
    backend.on('message', (data, isBinary) => {
      if (client.readyState !== WebSocket.OPEN) return;
      if (client.bufferedAmount > maxBuffered) return finish(1013, 'client too slow');
      client.send(data, { binary: isBinary });
    });
    client.on('close', (code, reason) => finish(code, reason));
    backend.on('close', (code, reason) => finish(code, reason));
    client.on('error', () => finish(1011, 'client error'));
    backend.on('error', (err) => {
      log('backend error:', err.code || err.message);
      finish(1011, 'game server unavailable');
    });
  }

  // True when something is listening on the backend port.
  function health() {
    return new Promise((resolve) => {
      const s = net.connect({ host: target.hostname, port: Number(target.port) || 80 });
      const end = (ok) => { s.destroy(); resolve(ok); };
      s.setTimeout(1000, () => end(false));
      s.once('connect', () => end(true));
      s.once('error', () => end(false));
    });
  }

  async function close() {
    if (timer) clearInterval(timer);
    for (const c of live) c.terminate();
    await new Promise((resolve) => wss.close(() => resolve()));
  }

  return {
    upgrade,
    health,
    close,
    stats: () => ({ live: live.size, accepted, rejected, target: target.href }),
  };
}

module.exports = { createWsProxy };
