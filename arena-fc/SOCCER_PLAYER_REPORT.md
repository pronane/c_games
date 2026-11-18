# Arena FC — Sprite Forge soccer player (mesh + skeleton + animations)

Built with the latest Sprite Forge on `main` (v11.13, PR #100 `891facd`).
The procedural primitive players are replaced — on desktop and in the browser
preview — by a sculpted footballer with a real skeleton and a clip for every
soccer move.

## What was built

| Artifact | Path | What it is |
| --- | --- | --- |
| Desktop player | `Data/models/soccer_player.glb` (3.1 MB) | Sculpted skinned mesh (16,000 tris) on Arena's 18-bone skeleton, 6 flat kit materials, **67 animation clips** |
| Browser player | `Data/soccer_rig.json` (1.2 MB) | Same mesh in the `rig_default.json` schema (10,488 verts), so the GDScript edition uses it with no glTF module |
| Manifest | `Data/soccer_player_manifest.json` | Clip list + loop flags, 75 action aliases, material order, build stats |
| Motion library | `Tools/soccer_motions.py` | 67 named clips: shipped Sprite Forge motions + 13 soccer-specific poses (shield, slide tackle, volley, header, chest control, trap, throw-in, shoulder charge, keeper ready/punch, toe lift, dribble, idle-ready) |
| Builder | `Tools/build_soccer_player.py` | Reproducible pipeline (below) |
| Tests | `Tools/test_soccer_forge.py` | 36 checks (stdlib-only GLB/JSON parsing; motion checks need `sprite_forge` on `PYTHONPATH`) |

## Pipeline

1. **Sculpt** — `sforge.footballer.design()` on the MakeHuman game skeleton
   (the same design `tools/gaelic_forge.py` uses): 122 SDF shapes, marching
   cubes at 6 mm, decimated to 16,000 tris, inverse-distance skin weights.
2. **Skeleton** — the 52 MakeHuman joint weights are collapsed onto Arena's
   18 bones (`Hips … RFoot`, identical to `Data/rig_default.json`) by nearest
   bind position. The mesh is grounded (min y = 0) and faces +Z.
3. **Animations** — every clip is baked on the Sprite Forge mannequin
   (`rigrec.from_mannequin`), then retargeted mannequin → Arena skeleton with
   `sforge.retarget` (in-place root motion; the engine owns translation).
4. **Materials** — flat colours per body layer (skin / jersey / shorts / socks
   / boots / hair) instead of a baked kit texture, so kits stay per-club:
   the C# loader tints them from `CharacterSpec` exactly like the procedural
   rig, and the browser recolors via its existing material slots.

## Runtime

- **Desktop (C#)** — `Scripts/Godot/SoccerClipRig.cs` loads the GLB with
  `GltfDocument`, sets loop modes from the manifest, and plays clips from
  `PlayerState`: one-shots (`kick`, `tackle`, `slide`, `dive`, `catch`,
  `foul`, `celebrate`) play once while their `ActionTimer` runs, otherwise
  locomotion by speed (`idle` / `walk` / `jog` / `run` / `sprint`),
  `dribble` / `shield` when close-controlling, `keeper_ready` for keepers.
  `RigFactory` attaches it (editor/self-test stay procedural);
  `RigAnimator.Pose` routes to it.
- **Locomotion (FIFA-style)** — cadence is matched to ground speed per clip:
  each clip's foot travel per 1 s cycle was measured from the GLB
  (walk 0.74 m, jog/run 1.01 m, sprint 1.22 m, dribble 0.60 m) and
  `SpeedScale = speed / natural rate` (clamped, smoothed) keeps foot speed
  ~= ground speed, so players no longer run on the spot or slide backwards.
  Bands have hysteresis (no threshold flicker), the dribble clip only plays
  while moving, one-shots never replay, and the body leans forward with
  speed/acceleration and rolls into turns. Each player has a stable style
  (stride ±7%, lean variation) seeded from their spec.
- **Browser (GDScript)** — `BrowserBoot` loads `Data/soccer_rig.json` first
  (same 18-bone schema), so the sculpted mesh is used with the existing
  procedural gait. The WASM template has no glTF module, so the GLB itself
  cannot load in the preview — the JSON is the browser path.

## Verification

| Check | Result |
| --- | --- |
| `Tools/build_soccer_player.py` | 122 shapes → 16,000 tris, 67 clips retargeted, GLB 3.1 MB, JSON 1.2 MB |
| `Tools/test_soccer_forge.py` (full, with Sprite Forge venv) | **41 passed, 0 failed** |
| `Tools/test_soccer_forge.py` (system python, stdlib only) | **36 passed, 0 failed** (motion section skips) |
| `Tools/test_pads.py` regression | **129 passed, 0 failed** |
| `gdparse` (BrowserBoot) + tree-sitter C# (3 changed files) | clean |
| WASM preview rebuilt + served | 35 staged files incl. `soccer_rig.json`; `/`, `godot.mjs`, `godot.wasm`, manifest all HTTP 200 |
| CI (`arena-fc-tests.yml`) | new `Sprite Forge soccer player checks` step; `dotnet-core` builds the C# loader |

## Limits / next steps

- The browser edition animates the sculpted mesh with the procedural gait;
  clip playback in GDScript (sample `soccer_*` clips from JSON) is the
  natural follow-up if both editions should play identical moves.
- Kit detail is flat colours (no baked texture/face paint), matching Arena's
  per-club kit system. A baked texture variant can be added with
  `gamemesh.bake` + `footballer.paints` without changing the skeleton/clips.
- All players share the 1.77 m base height; the C# loader scales the rig
  node by `CharacterSpec.Height`, so editor height edits still work.
- Native Windows rebuild + physical gameplay recording remain user-side
  checks (no `dotnet`/`godot` in the sandbox); CI compiles the C# loader.
