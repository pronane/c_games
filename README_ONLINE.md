# Deploy Online — HD Fighter 2 Multiplayer
Your game is **already playable online right now** on this sandbox (port 3000).
Share the preview URL — any device that opens it joins the same server (phone vs desktop).

## How to play
1. Device A: Create room / Quick Play → pick fighter → Ready
2. Copy Invite Link (`#R0001`) → send to Device B
3. Device B: Join by Code → pick → both Ready → Fight!

Controls: Desktop WASD+JKL etc, Phone joystick+buttons, Gamepad USB/BT on all.
Network: 60fps input relay, ping shown.

## Deploy to your GitHub (when you share it)
```bash
git remote add origin YOUR_URL
git push -u origin main
# Render: New Web Service → Build: npm install --prefix multiplayer → Start: npm start --prefix multiplayer
# Fly: fly launch --cwd multiplayer && fly deploy --cwd multiplayer
```
