# 🚀 Deploy — Get Your Permanent Online Link

Your game: **https://github.com/pronane/c_games** (replaces temp `e2b.app` sandbox).

### 1-Click Deploy (Render Free)
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/pronane/c_games)
1. Click → Log in → Authorize GitHub
2. **Root Directory:** `multiplayer`
3. Build: `npm install` | Start: `npm start` | Plan: **Free** → Create
Wait 2-3 min → `https://c-games-xxxx.onrender.com` → share `https://YOUR-URL#R0001`

### Alt — Fly.io (no sleep)
```bash
npm i -g flyctl; fly auth login; fly launch --cwd multiplayer; fly deploy --cwd multiplayer
# → https://c-games.fly.dev
```
### Cost (30Hz relay, 300B/msg): 1 room=65MB/h; 80 players×2h/day=156GB/mo (free fits); 100×2h=195GB (~$5)
