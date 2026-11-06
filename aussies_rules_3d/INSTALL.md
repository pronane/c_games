# Install — one click on every operating system

## macOS & Linux

```bash
./install.sh
./start.sh
```

That's the whole thing. `install.sh`:

1. finds Node 20+ — if the machine has none, it downloads a **private copy**
   into `~/.aussie-rules-3d/node` (nothing else is touched; delete that folder
   to undo),
2. installs the npm dependencies (three, vite, vitest, typescript),
3. verifies the 3D assets (rigged players, ball, arena) — regenerating them
   with Blender on request (`./install.sh --assets`).

`start.sh` builds the game and serves it at **http://localhost:8080**.
Options: `./start.sh --dev` (hot-reload development), `./start.sh --port N`.

No sudo is required at any point.

## Windows

Double-click **`install.cmd`** (or run `.\install.ps1` in PowerShell), then
double-click **`start.cmd`**. If Node is missing, the installer downloads a
private copy into `%USERPROFILE%\.aussie-rules-3d\node`.

## Then install it as an app (optional)

Open http://localhost:8080 in your browser and choose **Install app** (Chrome
/ Edge: the icon in the address bar; Safari: Share → Add to Home Screen). The
game then runs full-screen and offline like a native app on any device.

## Development setup

```bash
npm install       # dependencies
npm run dev       # dev server with hot reload
npm test          # 86 tests (laws, engine, input, sim)
npm run verify    # tests + types + build + asset checks
npm run assets    # regenerate the GLB models with Blender
```

Requires Node 20+. The asset pipeline additionally needs Python 3.10+ (it
creates its own venv and installs Blender-as-a-module `bpy` — ~300 MB,
one-time). Generated models are committed, so Python/Blender is **only**
needed when changing the models.

## Playing on other devices

Because `start.sh` listens on `0.0.0.0`, any device on your network can play:
open `http://<your-computer's-IP>:8080` on a phone, tablet or TV browser.

## Troubleshooting

| Problem | Fix |
|---|---|
| `Node 20+ is required` | Install Node from [nodejs.org](https://nodejs.org), or re-run `./install.sh` to auto-download |
| Black screen / WebGL error | Update your browser and GPU drivers; the game needs WebGL2 |
| Asset generation fails on a server | That's fine — the committed GLBs are used. To force regeneration on headless Linux, `node scripts/build-assets.mjs` runs the Blender pipeline with auto-built X/GL stubs |
| Gamepad not detected | Press any button on the pad while the game tab is focused (browser security) |
