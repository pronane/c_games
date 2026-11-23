# Squad GLB LOD candidate — `tools/out/gaelic_player.lod.glb`

**Status: candidate only. NOT shipped, NOT approved for the shipped asset path.**
`public/assets/gaelic_player.glb` is unchanged. This document is the record of
how to rebuild the candidate, what it contains and what still needs verifying
before anyone swaps it in.

## Why

All 22 players draw the full-detail squad: ~35 k triangles per look, ~318 k
squad-wide, at every camera distance. Arena FC solved the same problem with
Sprite Forge `skinlod` v11.38 (see `arena-fc/Tools/add_lods.py`); this bakes an
equivalent for AR3D using the same plan, with one deliberate deviation.

## Rebuild

```bash
python3 -m venv ../sfvenv && ../sfvenv/bin/pip install numpy pillow
../sfvenv/bin/python tools/build_afl_lods.py
```

Writes `tools/out/gaelic_player.lod.glb` (gitignored) + `tools/out/lod_report.json`.
Stages: (1) TEXCOORD_0-zero injection for the 36 kit primitives that ship
without UVs (tailor's `read_parts` requires them), (2) per `v0_..v8_` prefix
`skinlod.lod_parts` at 0.45 / 0.22 triangle ratios, (3) placeholder-UV strip
(untextured kit parts), (4) `bufferView.target` restoration. The shipped asset
is never written.

Deviation from the stock plan: `socks` gets `min_ratio (0.75, 0.70)`. The stock
plan collapses the shin tube to a chord (≈51 mm 95th-percentile surface drift
at both levels, all nine looks); with the bump the worst sock is ≈36 mm.

## What the candidate contains

- Full 32-clip animation set, single skin, **52 joints** (contract unchanged).
- Every appearance variant keeps its `vN_…` node names; LOD meshes add
  `<part>_lod1` / `<part>_lod2` nodes on the same skin + material (runtime kit
  tinting and variant pruning match by suffix-tolerant name — see
  `src/render/lod.ts`).
- Triangle budget (squad-wide): **318 539 → LOD1 161 499 (51 %) → LOD2 96 886 (30 %)**.
- Size: 19.3 MB → **28.9 MB** (+9.6 MB).
- Khronos glTF validator: **0 errors / 0 warnings / 0 infos** (shipped asset:
  0/0/0). Worst surface deviation (95th-pct, vertex-based): ≈37 mm (jersey /
  shorts L2); socks ≈36 mm after the bump. Same class as the shipped Arena FC
  bake.

## Runtime wiring (already in the game, asset-agnostic)

`src/render/lod.ts` + `syncPlayerViews(..., camera)`:
- `collectLodKits(root)` groups `x` / `x_lod1` / `x_lod2`; empty list with the
  shipped asset → **zero behaviour change**.
- Selection per player per frame: `pickLodLevel(distance, LOD_DISTANCES[this.lodQuality])`.
  Tiers — ultra [22, 48], high [16, 36] (default), performance [11, 26] — chosen in
  settings → Graphics quality (`sel-graphics`, applied live, mirrors
  `LOD_PLAN['distances_m']` in Sprite Forge).
- LODs are hidden until a camera distance demotes; visibility flips only on
  level change. Kit tinting strips the `_lodN` suffix before suffix matching
  so LODs get the same tint + squad number.

## Before anyone ships this (approval required)

1. **Explicit user decision** to replace `public/assets/gaelic_player.glb`.
2. Browser/GPU check: variant switching, tint, LOD swaps at distance, shadows.
   Not done — no browser automation in this environment; unverified.
3. FPS/GPU-time measurement at broadcast distance (LOD2) and wing distance.
4. Graphics-quality setting shipped (settings → Graphics quality). The
   toggle is inert until the LOD candidate actually ships — the shipped GLB
   carries no `_lodN` nodes, so every tier renders full detail.
5. LOD2 drop-outs (`lashes` / `brows` / `hairinner`) and openings should get a
   human look — expected invisible at broadcast distance, unverified.

## CI: Aussies Rules Motion A/B

`.github/workflows/aussies-rules-motion-ab.yml` (`.github/workflows/…`) — manual
(`workflow_dispatch`) plus push/PR when `aussies_rules_3d/**` changes.

- **ab-metrics** (authoritative): `npm ci` → `check.mjs` → re-bakes the LOD candidate
  from the shipped asset (`tools/build_afl_lods.py`) → Khronos validator on both GLBs →
  squad-contract A/B table (`tools/ab_report.py`: sizes, joints, clips, clip parity,
  per-look triangles, LOD node count, material parity). Fails red on contract breaks;
  the report lands in the job summary; LOD GLB + JSON/MD reports upload as artifacts.
- **visual-ab** (experimental, `continue-on-error`): builds the web bundle, then under
  xvfb + SwiftShader (`LIBGL_ALWAYS_SOFTWARE=1`) loads the title/attract demo in
  Electron twice — shipped asset vs LOD asset swapped in — captures 24 frames each
  (`tools/ci_capture.cjs`), assembles MP4s with ffmpeg, uploads frames/mp4s/console
  logs as the `aussies-rules-motion-ab-visual` artifact. Software WebGL is plausible
  but unverified end-to-end; treat this leg's output as diagnostic, and keep the
  shipped asset untouched either way. A companion PR adds the `?ab=1` capture
  mode (`src/main.ts`): fixed attract seed so both legs simulate the identical
  match, menu overlays hidden, and `AB_STATS` renderer counters logged every
  ~2 s; with `--query ab=1` in `ci_capture.cjs` the captures become
  frame-comparable between the two legs.
