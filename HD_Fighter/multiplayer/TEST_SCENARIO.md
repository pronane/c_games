# HD Fighter 2 — Mandatory Post-Change Test Checklist

> **This checklist MUST be run after ANY change to `multiplayer/` (server, index.html, game.js, assets). A change is not considered verified until all phases pass.**

**Live URL:** `https://hd-fighter-2.onrender.com/`  
**Commit under test:** `git rev-parse HEAD` (paste here before running)

---

## Phase 1: Room Setup (2 browsers)

| # | Action | Expected Result | Pass |
|---|--------|-----------------|------|
| 1 | Open URL on **Browser A** (desktop Chrome) | Site loads, `netpill` = **online** (green), `roompill` = **no room** | ☐ |
| 2 | Open same URL on **Browser B** (iPhone Safari) | Same as above | ☐ |
| 3 | Browser A: **Create Private Room** | Room code appears (e.g. `R0001`), `Leave Room` shows, `status` = `Room R0001 as P1` | ☐ |
| 4 | Browser A: **Copy Invite Link** | Link copied (or shown in status) | ☐ |
| 5 | Browser B: Paste link or enter code → **Join by Code** | `status` = `Joining R0001…` → `Room R0001 as P2` | ☐ |
| 6 | Browser A: Wait | Both show `Opponent joined! Pick fighters.` + `roomInfo: Room R0001 — 1/2 …` | ☐ |

**Fail = STOP. Check Render `online`, hard-refresh `?v=` , DevTools Console for `WSS` errors.**

---

## Phase 2: Character Picking

| # | Action | Expected | Pass |
|---|--------|----------|------|
| 7 | Browser A: Tap **KAIRO** | Yellow border, `pickInfo` = `You: KAIRO — hit Ready`, `Ready` enables | ☐ |
| 8 | Browser B: Tap **LYRA** | Same for P2, `vsLine` = `VS KAIRO (You) vs LYRA — both picked, hit Ready` | ☐ |
| 9 | Both: `vsLine` visible | Shows both names, `roomInfo` = `Room R0001 — 2/2 | P1: KAIRO …pick | P2: LYRA …pick` | ☐ |
| 10 | Browser A: **Ready** | `readyBtn` disabled, `pickInfo` = `Ready! Waiting… Server will confirm`, `roomInfo` → `P1: KAIRO ✅` | ☐ |
| 11 | Browser B: **Ready** | Same, `roomInfo` → `P1: KAIRO ✅ P2: LYRA ✅ — both Ready → starting…` | ☐ |
| 12 | Both | `status` shows `2/2`, `start` received, `gameScr` visible | ☐ |

**If both show `Ready` but no `start`, check: `api/health` rooms, `roomInfo` line (`1/2` vs `2/2`), `netpill` must be `online`, `DevTools → Console` for `Pick a fighter first` / `Waiting…` errors.**

---

## Phase 3: Fighting

| # | Action | Expected | Pass |
|---|--------|----------|------|
| 13 | Watch timer | Counts `99 → 98` every second | ☐ |
| 14 | Both fighters render | KAIRO & LYRA sprites visible (192×256 HD, not blank, not strips) | ☐ |
| 15 | Browser A: `WASD+JKL` | P1 moves/attacks | ☐ |
| 16 | Browser B: Touch d-pad + `LP/HP` | P2 moves via `▲ ◀ ▼ ▶` + buttons | ☐ |
| 17 | Land a hit | HP bar drops, hitstop + sparks | ☐ |
| 18 | Check `ping` | `~170–200 ms` shown | ☐ |

---

## Phase 4: Reconnect (Critical Bug Test)

| # | Action | Expected | Pass |
|---|--------|----------|------|
| 19 | Browser A: Close tab / airplane ✈️ 3s | Browser B shows `P1 left` (yellow) | ☐ |
| 20 | Browser A: Reopen same link `/#R0001` | Auto-rejoin via `hd2_userId`+`hd2_room`, **same slot/team**, `roomInfo` restores picks | ☐ |
| 21 | If was fighting | Same tick, HP, positions resume | ☐ |
| 22 | If was in lobby | Both `ready` reset → `roomInfo` shows `…pick` not `✅`, no false `2/2 ready` (verifies `leave() {r.ready[slot]=false}`) | ☐ |

---

## Phase 5: Controls Layout (iPhone Safari portrait)

| # | Action | Expected | Pass |
|---|--------|----------|------|
| 23 | Portrait: Touch visible | `▲` above `▼`, `◀ ▼ ▶` middle row, `LP TH HK` bottom row | ☐ |
| 24 | D-pad cross | `▲` not stranded, proper cross `LK ▲ HP` / `◀ ▼ ▶` / `LP TH HK` | ☐ |
| 25 | Tap buttons | Yellow flash on press, `pointer-events` works | ☐ |

**iPhone portrait MUST keep `grid-template-columns:repeat(3,52px)` (not 4) and `grid-template-rows:repeat(3,52px)` with `grid-column/row` for `up/left/down/right`.**

---

### How to run (copy-paste)

```bash
# 1. Hard-refresh both: Chrome Cmd+Shift+R, Safari → Clear History → Incognito
# 2. Do Phases 1–5 above, ticking each row
# 3. If Phase 2 fails → paste new `roomInfo` line here: ____________________
# 4. Screenshot `lobby` + `fight` and attach to PR
```

### Automatable (optional)

`npm --prefix multiplayer test` or Playwright `test:e2e` should replicate Phases 1–5 headless (390×844 mobile + 1280×720 desktop, two contexts, same `userId` persistence).

