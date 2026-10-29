# 🎮 HD Fighter 2 — Original HD Fighting Game + Online Multiplayer

**Street-Fighter-style, 100% original art.** 6 fighters, 3 parallax stages, 60fps HD (192×256) — now **playable online vs anyone on any device**.

### ⚡ Play Online NOW (multi-device)
**Live:** `https://3000-itltc005egaw9tuy0yd42.e2b.app` *(this sandbox — your permanent URL comes after deploy below)*
1. Device A: **Create Private Room** → pick KAIRO/LYRA/NAOMI/BRUTUS/VOID/ZAP → **Ready**
2. **Copy Invite Link** (`#R0001`) → send to Device B (phone/desktop/tablet)
3. Device B: **Join by Code** → pick → both **Ready** → **Fight!** — touch joystick + gamepad on all.

No install. Share link = share room. `⚡ Quick Play` also auto-matches.

### 📱 Demo Video (2 phones)
`screenshots/phones_demo.mp4` — 10s 60fps KAIRO vs LYRA with phone overlays (gold=Phone A touch, green=Phone B desktop) in one WebSocket room.

### 🎯 What you get
- 6 original fighters (KAIRO full-body, LYRA, NAOMI, BRUTUS, VOID, ZAP) — 16 states each (idle5 walk7 crouch2 jump5 lp4 hp5 lk4 hk5 block2 throw5 hit3 special1/2 super7 win5 lose3)
- Combat: hit-stop, screen-shake, hit sparks, combo counter, block stun, throws, super moves
- 3 parallax stages (ROOFTOP/TEMPLE/INDUSTRIAL) with animated foreground
- Online: Node.js WebSocket server (`multiplayer/server.js`), 60fps input relay, rooms + quick-play, ping, deployable

### 📦 Run Locally
```bash
pip install -r requirements.txt
python game.py          # local 2P (WASD+JKL / Arrows+Pad / 2 gamepads, F2 toggles HD/CLASSIC)
# Online server:
cd multiplayer && npm install && npm start   # → http://localhost:3000
```

### 🌐 Export to 6 Platforms
| Platform | Command | Output |
|----------|---------|--------|
| Windows | `export_desktop/build_release.bat` | `dist/HD_Fighter_2.exe` (PyInstaller) |
| Linux/macOS | `./export_desktop/build_linux.sh` | `dist/HD_Fighter_2` |
| Web/Browser | `pip install pygbag && pygbag --archive .` | `build/web/` → itch.io |
| Android | `cd export_android && buildozer android debug` | `bin/*.apk` |
| iOS | `export_ios/build.sh` (PWA) | Add to Home Screen, or `kivy-ios` native |

### 🚀 Deploy Your Own Online Server (free)
**Render (1-click):** Connect this repo → New Web Service → Root: `multiplayer` → Build: `npm install` → Start: `npm start` → Free 750h/mo
**Fly.io:** `fly launch --cwd multiplayer && fly deploy`
**Docker:** `docker build -f multiplayer/Dockerfile multiplayer -t hd2 && docker run -p 3000:3000 hd2`

### 📸 Proof
`screenshots/tournament_30s.mp4` (30s 4-match CPU tourney), `screenshots/phones_demo.mp4` (10s online 2-phone), `screenshots/comprehensive_gallery.html` (96 move grids + 6 comp videos), `screenshots/phones_player.html`

No Capcom assets — all sprites procedurally generated original (see `generate_assets*.py`).
