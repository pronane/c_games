# Arena FC — Option B deployment notes

## Prerequisites
- A paid Render plan (Starter or above) — Docker/Web Services are not available on Render free tier.
- Your Arena FC repo on GitHub with the `Server/` (.NET) and `edge/` (Node proxy) folders.
- Godot WASM web export at `build/web/` (export from Godot 4 with the Web export template).

## What changes in Arena FC source

### 1. .NET server (`Server/Program.cs`)
Bind to localhost only — Render exposes the Node edge on the public PORT; .NET is internal:
```csharp
// Example: read a fixed internal port; do NOT bind to Render's public PORT
var builder = WebApplication.CreateBuilder(args);
builder.WebHost.UseUrls("http://127.0.0.1:7777");
```
The .NET server ignores `PORT` (Render injects it for the Node edge). It binds to `127.0.0.1:7777`.

### 2. Godot client (`Web/NetClient.gd`, `Web/BrowserBoot.gd`)
Change the WebSocket URL from `ws://` to same-origin `/ws` so HTTPS pages can connect:
```gdscript
# Instead of prepending "ws://" (blocked by browsers on HTTPS):
var net_url := "/ws"  # same-origin, upgrades to wss:// automatically
```
In `BrowserBoot.gd`, default `net_url` to `"/ws"` and build invite links as `https://host/#CODE`.

## Deployment steps
1. Push `Dockerfile`, `render.yaml`, `edge/`, `Server/`, and `build/web/` to GitHub.
2. In Render: Create → Web Service → Connect GitHub repo.
3. Environment: Docker. Dockerfile path: `./Dockerfile`.
4. Plan: Starter (minimum for Docker).
5. Health check path: `/health`.
6. Render will build the image, start .NET on `127.0.0.1:7777` and Node on `$PORT`.
7. Share `https://arena-fc.onrender.com/#ROOMCODE` with players.

## Caveats
- Render free tier: **cannot** run Docker, so Option B is not possible there.
- Rooms/WebSockets are in-memory in the .NET server; a Render restart drops active matches.
- For production, add Redis-backed room state and multiple instances behind Render's load balancer.
