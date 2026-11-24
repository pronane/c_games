# Motion: stride limit & planted-foot IK

**Status:** implemented, unit-tested, **not visually verified** — the planted-foot IK is
flag-gated (`?plantik=1`) and off by default until a GPU/browser pass signs it off.
No "feet no longer slide" or perf claims are made until that happens.

Ported from the Gaelic branch's `strideLimit()` / `plantOne()` / `stretchLeg()`
(`Gaelic_Football_3d/src/main.c`, constants `GA_LEG_MAX_STRIDE_SCALE = 1.55`,
`GA_LEG_MAX_REACH = 0.95`).

## What is wired today (unconditionally)

- **Stride limit on locomotion playback.** `MotionEngine.playbackScale()` for
  locomotion clips used to return `clamp(speed / preferredSpeed, 0.45, 2.8)` —
  a 7 m/s sprint on a jog clip demanded a 2.8× cadence, i.e. locked, over-extended
  knees. Now the upper clamp is `min(2.8, strideLimit(speed))` where
  `strideLimit(speed) = 1 + 0.55 * clamp01((speed - 1) / 6)` (1.0 at ≤ 1 m/s →
  1.55 at ≥ 7 m/s). Faster-than-reach speeds now under-play the cycle (the feet
  slide a little) instead of forcing the pose — the Gaelic trade-off, ported
  verbatim. `advancePhase` and all crossfade machinery are unchanged.
- **glTF→three write-back path for 2-bone leg IK** (`solveLegChainWorld`,
  `aimBoneWorld` in `render/motionBinding.ts`): thigh is re-aimed (quaternion
  from→to), the calf joint is placed at the solved knee, the calf is re-aimed,
  and the foot joint is placed at the solved target. Foot orientation stays as
  authored. Validated on a synthetic yawed chain (see tests).

## What is implemented but flag-gated (`?plantik=1`)

- **Planted-foot anchor & hold.** Per leg, a world-space state machine
  (`updatePlantSide` in `motion/legIk.ts`, a faithful port of Gaelic `plantOne`):
  - foot above 0.20 m → plant released; below 0.11 m and plant weight nearly
    zero → plant (anchor = foot world position, y ignored).
  - `am_smooth` exponential fade on plant weight (0.07 s attack / 0.09 s
    release — same response times as Gaelic).
- **Stance-foot IK.** The authored foot pose is blended toward the ground
  anchor by plant weight; the leg chain is re-solved with a reach clamp
  `(l1+l2) × 0.95` (`GA_LEG_MAX_REACH`) around the hip. If the hip cannot
  reach the anchor, the plant releases (this is the push-off).
- **Knee pole:** authored knee direction is preserved while it is forward of
  the hip→target line; otherwise model-forward (facing) projected ⊥ hip→target.
  Ports Gaelic `legPole` including its degenerate-case behaviour.
- **Busy gate:** one-shot leg actions (kick/tackle/etc. via the forced-clip
  path) and speeds < 0.45 m/s disable planting — the authored foot is kept.

## Honest verification status

| Claim | Status |
|---|---|
| Pure math correct (stride curve, am_smooth, reach clamp, state machine) | ✅ unit tests `tests/legIk.spec.ts` (19) |
| World-space chain solve lands foot on target, preserves segment lengths, deterministic | ✅ unit tests `tests/plantIk.spec.ts` (5) on a synthetic yawed rig |
| glTF bone-name lookup (`thigh_l`…), flag parsing | ✅ same tests |
| Feet visibly stay planted in-game; no mesh shear | ❌ **not verified** — no GPU in this environment |
| No frame cost regression | ❌ not measured (see perf harness in the visual-ab workflow — software WebGL tripwire only) |

**To A/B visually:** `?ab=1&plantik=1` vs `?ab=1` (attract demo, fixed seed).
Motion quality also needs the squad LOD/guernsey checks — see the
`GAP_ANALYSIS_PS5.md` P0 "verify gap" item; a human with a browser must sign off.

## Known limitations

- The squad GLB has **no toe bones** (thigh/calf/foot only). Gaelic also
  translated toe bones post-solve; that step is skipped, so the foot keeps its
  authored pitch.
- Flat-pitch assumption: ground is `y = 0`, root sits on it, plant height is
  hard-coded to 0.08 m (`rel.y = 0.08` in Gaelic).
- Legs only. Arms were folded into Gaelic's same solver but are not touched here.
- IK runs **after** `mixer.update(dt)` and after the root transform is set for
  the frame (see `syncPlayerViews` in `render/players.ts`).
- `?plantik=1` on a kick/tackle/mark one-shot disables planting entirely
  (matches Gaelic `legBusy`).
- Plant state is per-binding (per player, per session); it is not serialised.
