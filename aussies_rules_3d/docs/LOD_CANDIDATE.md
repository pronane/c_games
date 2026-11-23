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
- Selection per player per frame: `pickLodLevel(distance, LOD_DISTANCES.high)`
  = [16 m, 36 m] (`ultra` [22, 48], `performance` [11, 26] available).
- LODs are hidden until a camera distance demotes; visibility flips only on
  level change. Kit tinting strips the `_lodN` suffix before suffix matching
  so LODs get the same tint + squad number.

## Before anyone ships this (approval required)

1. **Explicit user decision** to replace `public/assets/gaelic_player.glb`.
2. Browser/GPU check: variant switching, tint, LOD swaps at distance, shadows.
   Not done — no browser automation in this environment; unverified.
3. FPS/GPU-time measurement at broadcast distance (LOD2) and wing distance.
4. Optional: a graphics-quality setting (ultra/high/performance) in the
   settings screen; distances are currently a constant (`LOD_DISTANCES.high`).
5. LOD2 drop-outs (`lashes` / `brows` / `hairinner`) and openings should get a
   human look — expected invisible at broadcast distance, unverified.
