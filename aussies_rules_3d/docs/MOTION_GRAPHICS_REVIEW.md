# Graphics & Hypermotion Engine — engineering review

**Branch:** `arena/b13a2d7a-c-games` · **Base:** `959541a` (`main`) · **Date:** 2026-11-07
**Scope:** aussies_rules_3d Phases 0–4 (compression, arena presentation, AFL motion assets, TS motion engine)

This is the record behind the "bring Aussie Rules 3D up to the Arena FC standard" work.
Numbers below were measured on this machine or computed from the committed artifacts;
everything not measurable headlessly is marked **UNVERIFIED** rather than asserted.

---

## 1. What shipped

| Phase | Deliverable | Evidence |
|---|---|---|
| 0 | brotli/gzip static serving (`scripts/start.mjs`); squad GLB contract gate; kit-tint verified | commits `10990ee`; `node scripts/check.mjs` → 5/5 |
| 1 | IBL (RoomEnvironment PMREM), LED perimeter ribbon (72 chord planes, scrolling canvas textures, fictional sponsors), `updateLedScorebug()`, blob contact shadows (players + ball) | commit `10990ee` |
| 2 | 11-clip AFL library authored & retargeted (mark contest, spoil, fend-off, ruck tap, snap kick, throw-in, bounce→pickup, siren + set-shot celebrations, bounce-in-stride, 50 m walk) | commit `510da82` |
| 3 | TypeScript port of the Arena Motion Engine + baked AFL schema-v2 assets + players/main wiring + vitest suite | commits `5f71969`, `5e84629` |
| 4 | This review, parity/robustness suite, README doc-drift fix | this commit |

## 2. Measured numbers

**Assets (brotli, quality 5, this machine):**

| File | Raw | br |
|---|---|---|
| gaelic_player.glb (52 joints, 32 clips, 249,005 tris, 62 meshes, 25 images) | 18.81 MB | 13.37 MB |
| stadium.glb | 2.57 MB | 0.27 MB |
| ball.glb | 0.10 MB | 0.02 MB |
| afl_motion.json (32-clip manifest) | 10.7 KB | ~0.3 KB |
| afl_motion_features.json (1273 rows × 24 dims) | 330 KB | ~51 KB |

**Feature table:** 1273 rows from the 32 shipped clips; 24 dims (facing-root XZ,
z-score normalised, trajectory horizons 0.2/0.4/0.6 s, `time_to_contact` weight 12.0).
One-shot categories contribute entry frames only (≤ contact). Non-loop Locomotion rows
are excluded from the gait search.

**Search cost:** O(1273) per query, ~1.4 MFLOP/s at 10 Hz × 18 players — noise vs. the
render loop. Brute force is deliberate (exact, deterministic); an IVF variant exists in
arena-fc's tools for larger tables.

**Tests:** 105 vitest cases green (94 prior + 11 parity/robustness) — no timers, no RNG
streams, fully deterministic. `npx tsc --noEmit` clean. `node scripts/check.mjs` → all 5
gates (TypeScript, test suite, production build, GLB validity, 52-joint/32-clip/v0–v8
squad contract).

**Candidate AFL GLB (Phase 2, NOT shipped):** `tools/out/gaelic_player.afl.glb`, 20.2 MB,
43 clips. Retarget mean direction error **0.00°** on all 11 new clips; round-trip through
`gltfread` verified (finite skinned world transforms); numeric leap check:
mark contest pelvis 0.73 → 1.37 m, ruck tap → 1.37 m, spoil → 1.24 m.

## 3. Rejected / failed approaches (kept, so they are not retried)

- **Meshopt-quantized gaelic_player.glb** — fails readback verification
  (phantom skins, NaN positions, |Δanim| ≈ 32767). Reverted byte-identical; meshopt is
  out until a meshopt-aware reader + three.js runtime smoke exists. Compression answer
  stays brotli at the static server.
- **arena-fc's `boneCount == 18` manifest gate** — not ported; the GAA rig has 52 joints.
- **Measured per-frame root velocities from the in-place clips** — sub-0.3 m of pelvis
  travel per cycle, so central differences are noise; the baker falls back to authored
  preferred-speed profiles (deterministic, matches `preferredSpeed` semantics).
- **`keeper_idle` in the outfield Idle category** — the idle search picked it; recategorised
  to Keeper and re-baked.
- **UI freeze via one-shot end poses** — approach/pickup rows are not valid gait keys;
  loose balls read as ball=None in the gait path. Actual pickup wind-ups fire from sim
  events (forced clips) only.

## 4. Verification status — honest list

**Verified (headless):** TypeScript compiles; 105/105 tests; production build; GLB
validity + squad contract; feature-table parse; search parity vs. an independent
brute-force reference; query-builder golden values; retarget direction error; candidate
round-trip; brotli sizes above.

**NOT verified (needs a browser/GPU or the user):**
- Whether the fallback path vs. motion-matched path looks right in motion (no WebGL here).
- All 11 new clips are authored blind — anatomy, balance, ball-hands tracking are
  **not visually confirmed**. Numeric checks (pelvis rise, ball keys, turf clearance) pass.
- No FPS/frame-time measurements exist on real hardware; the 18.8 MB 249k-tri squad is a
  heavy download (13.4 MB br) and will need LOD1/LOD2 (`skinlod`) for weaker devices.
- Foot IK is **not** wired — the GAA rig ships no IK effectors; clip phases are the ground
  truth and "foot plants" are exposed to FX/audio but not solved on the skeleton.
- Per-player gait variety is a deterministic 0.94–1.06 playback-scale jitter, not authored
  gait variants.
- Motion-matching parity against the C# build was **not executed** (no .NET runtime in
  this environment); the port is a line-by-line transliteration checked by golden values
  and an independent reference implementation, and arena-fc CI remains the C# gate.
- Contact fractions / preferred speeds / loop flags in `tools/afl_clip_meta.py` are
  **authored estimates**, not motion-measured — they drive `time_to_contact`.

## 5. Pending decisions & remaining work

1. **Ship the candidate AFL GLB?** Swapping `public/assets/gaelic_player.glb` flips:
   the check.mjs squad contract (32 → 43 clips), the manifest/features bake
   (`afl_motion.json`, `afl_motion_features.json`), `afl_clip_meta.py` (11 new entries),
   and the download weight (+1.4 MB). Not done without explicit approval.
2. **Motion-matched kick selection** — currently every kick one-shot forces `kick_run`;
   context (set shot vs. snap vs. behind) should route to `drop_kick` / `afl_snap_kick` /
   `kick_place` once the game emits that intent.
3. **Phase 1 leftovers** (unchanged, still open): `skinlod` LOD 1/2 bake, `skinshade`
   close-up maps + iris grade, two-tone mowed-turf shader, cloth flutter (TEXCOORD_1),
   officials (3 umpire sets + signal clips), crowd far LOD.
4. **Doc drift** — fixed for README this turn; `INSTALL.md`/`build-assets.mjs` internal
   comments still reference the legacy 19-bone path in places.
5. **PR** — this branch has not been opened as a PR; PR #133 (`arena/a4cb6d1c-c-games`,
   the soccer rebuild) remains the only open PR and is not this work's vehicle. Opening
   a PR for `arena/b13a2d7a-c-games` needs explicit instruction.
6. **100STYLE locomotion data** (CC BY 4.0) — not used; if it ever is, attribution must
   ship in the notices. Research-only sources (SkillCorner, SoccerTrack, Veo) remain
   unshipped.
