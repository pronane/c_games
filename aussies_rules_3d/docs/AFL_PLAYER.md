# AFL player assets — what shipped, what's pending

**Shipped in this branch (runtime):** every club renders a proper AFL guernsey —
club pattern (vertical stripes / hoops / sash / lace-up collar), big squad number
with contrast outline, painted on a canvas at load time per player
(`src/render/guernsey.ts`, patterns per club in `src/ui/ui.ts`). Guernsey
preview (offline re-draw of the same painting code): `tools/out/guernsey_preview.png`
(gitignored) — all 12 clubs read as AFL. Jersey UVs come from `src/render/jerseyUvs.ts`.

The shipped mesh is **unchanged** — `public/assets/gaelic_player.glb` is still the
Gaelic-pipeline sculpt from PR #247. No file was replaced.

**Pending (needs a networked machine): the NEW AFL squad GLB.**

`tools/build_afl_player.py` builds `public/assets/afl_player.glb` from the same
MakeHuman CC0 identities as the Gaelic squad (`Gaelic_Football_3d/assets/source/squad.txt`),
but with AFL guernsey kit paints (`sf_*@guernsey`: sleeveless cut, white yoke,
lace-up collar). The 52-joint skeleton, 32 clips and nine-look (`v0_..v8_`)
contract are identical, so `scripts/check.mjs` and the runtime need no changes.
At runtime the per-club guernsey canvas always wins for the jersey; the baked
atlas is a fallback only.

It cannot run here: the MakeHuman CC0 assets download from
`files.makehumancommunity.org`, which is not reachable from this repo's CI/sandbox
(egress allowlist: github / npm / pypi only). On a networked machine:

    python3 sprite_forge/forge.py human --setup --full      # one-time
    ../sfvenv/bin/python tools/build_afl_player.py --out tools/out            # build only
    ../sfvenv/bin/python tools/build_afl_player.py --out tools/out --install  # + copy to public/assets/

The game **prefers** `afl_player.glb` when present and silently falls back to
`gaelic_player.glb` otherwise (`src/main.ts`), so `--install` + deploy is all that
is needed to flip the squad over. Nothing else to change.

## Verification status (honest)

- Runtime guernseys: painting code is unit-tested for geometry (`tests/guernsey.spec.ts`);
  the exact canvas code is browser-unverified (no browser in this environment).
  The 12-club preview image is a PIL re-draw, not the real code.
- `tools/build_afl_player.py`: **not executed end-to-end** (MakeHuman library absent).
  It is a careful adaptation of `sprite_forge/tools/gaelic_squad.py` with a defensive
  fallback (kit-atlas bake failure → neutral grey atlas; the runtime paints guernseys
  anyway), but expect to debug paths/imports on first run. After running it, verify:
  1. `node scripts/check.mjs` (the contract gate extends to afl_player.glb if you add it — see below),
  2. club patterns + numbers in a browser,
  3. nine distinct looks survive (`check.mjs` requires v0_..v8_).
- Suggested when you run the bake: add a `public/assets/afl_player.glb` branch to the
  check.mjs asset-validity and squad-contract blocks so the new file is gated the same
  way (one paragraph of code; left out now because the file does not exist yet and the
  gate would fail on a fresh clone).

## What "new AFL players" means here

- ✅ New AFL-look rendering at runtime for all 12 clubs (this branch).
- ✅ New-asset path (`afl_player.glb`) with game-side auto-preference + fallback (this branch).
- ⏳ New baked squad (fresh mesh, new kit atlases): one command on a networked machine (above).
- ❌ From-scratch skeleton/rig: out of scope — the shared 52-joint rig carries the
  AFL mocap clip library (mark, spoil, fend, ruck tap, snap, siren) that already retargets to it.
