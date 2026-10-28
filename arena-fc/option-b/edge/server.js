// Arena FC — Node static edge + WebSocket proxy
//
// Public (Render):   https://arena-fc.onrender.com:$PORT
//   GET  /           -> Godot WASM static build (build/web)
//   GET  /health     -> health check
//   WS   /ws         -> proxy to ws://127.0.0.1:7777 (.NET authoritative server, internal only)
//
// Internal:          ws://127.0.0.1:7777  (.NET server, not exposed publicly)

const express = require('express');
const { createProxyMiddleware } = require('http-proxy-middleware');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 10000;

// ---------------------------------------------------------------------------
// Headers required for Godot WASM export (threads / SharedArrayBuffer)
// ---------------------------------------------------------------------------
app.use((req, res, next) => {
  res.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
  res.setHeader('Cross-Origin-Embedder-Policy', 'require-corp');
  res.setHeader('Cache-Control', 'no-store');
  next();
});

// ---------------------------------------------------------------------------
// Static Godot WASM build (export your web build to build/web/)
// ---------------------------------------------------------------------------
app.use(express.static(path.join(__dirname, '..', 'build', 'web'), { maxAge: 0, etag: false }));

// ---------------------------------------------------------------------------
// Health check (Render uses this)
// ---------------------------------------------------------------------------
app.get('/health', (_req, res) => {
  res.json({ ok: true, service: 'arena-fc-edge' });
});

// ---------------------------------------------------------------------------
// WebSocket proxy: wss://arena-fc.onrender.com/ws -> ws://127.0.0.1:7777
// Browser clients connect to same-origin wss://, avoiding mixed-content blocks.
// ---------------------------------------------------------------------------
app.use('/ws', createProxyMiddleware({
  target: 'http://127.0.0.1:7777',
  ws: true,
  changeOrigin: true,
  logLevel: 'warn',
  // Forward the original host so .NET can see the real origin if needed
  selfHandleResponse: false,
}));

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------
const server = app.listen(PORT, '0.0.0.0', () => {
  console.log(`Arena FC edge listening on http://0.0.0.0:${PORT}`);
  console.log(`  Static:  https://arena-fc.onrender.com/`);
  console.log(`  Health:  https://arena-fc.onrender.com/health`);
  console.log(`  WS proxy: wss://arena-fc.onrender.com/ws  ->  ws://127.0.0.1:7777 (.NET)`);
});

server.on('error', (err) => {
  console.error('Edge server error:', err);
  process.exit(1);
});

// Graceful shutdown
process.on('SIGTERM', () => {
  console.log('SIGTERM received, shutting down...');
  server.close(() => process.exit(0));
});
