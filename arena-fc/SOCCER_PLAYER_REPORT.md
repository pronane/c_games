# Arena FC — Sprite Forge soccer player (mesh + skeleton + animations)

Built with the latest Sprite Forge on `main`.

* 2026-11-18: rebuilt with Sprite Forge **v11.17** (`49be53a`), which brings the
  v11.14–v11.17 head/face/hair fixes (face joins the head, no tiled hair texture,
  collar stays below the jaw, white balance from a neutral garment, face colour
  matched to skin). 71 clips / 82 aliases now ship (was 67 / 75).
* Original: v11.13 (PR #100 `891facd`).
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
  (same 18-bone schema). The WASM template has no glTF module, so the GLB
  itself cannot load in the preview — the JSON is the browser path, and it
  now carries the same 67 clips baked as keyframes (2.0 MB). `BrowserBoot`
  plays them with the same cadence matching as desktop (per-clip natural
  rates, hysteresis bands, one-shots once, lean/roll from acceleration),
  falling back to the procedural gait if clips are absent.

## Verification

| Check | Result |
| --- | --- |
| `Tools/build_soccer_player.py` | 122 shapes → 16,000 tris, 67 clips retargeted, GLB 3.1 MB, JSON 2.0 MB (mesh + baked clips) |
| `Tools/test_soccer_forge.py` (full, with Sprite Forge venv) | **52 passed, 0 failed** |
| `Tools/test_soccer_forge.py` (system python, stdlib only) | **36 passed, 0 failed** (motion section skips) |
| `Tools/test_pads.py` regression | **129 passed, 0 failed** |
| `gdparse` (BrowserBoot) + tree-sitter C# (3 changed files) | clean |
| WASM preview rebuilt + served | 35 staged files incl. `soccer_rig.json`; `/`, `godot.mjs`, `godot.wasm`, manifest all HTTP 200 |
| CI (`arena-fc-tests.yml`) | new `Sprite Forge soccer player checks` step; `dotnet-core` builds the C# loader |

## Option 2 (2026-11-18) — the realistic player

Pulling the latest `main` (`49be53a`) made the "sculpted mannequin" route a
known quantity: rebuilding it with the newest Sprite Forge (**v11.17**) yields a
byte-identical GLB — v11.14–v11.17 only touched the capture/scan head path, not
the `sforge.footballer` sculpt. So the visible step-change is a new build:

| Artifact | Path | What it is |
| --- | --- | --- |
| Realistic GLB | `Data/models/soccer_player.glb` (12.8 MB) | **MakeHuman-derived footballer** from `Gaelic_Football_3d/assets/models/gaelic_player.glb` (same source GAA/AFL/Hurling use): real anatomy mesh, baked skin/eye/hair/beard atlases, smooth normals, **52-joint MH skeleton** incl. fingers, ball-of-foot, neck |
| Browser rig | `Data/soccer_rig.json` (12.1 MB) | Same player in the `rig_default.json` schema (v0 base, `variant_sets` for v2/v6) + all 71 clips baked for the GDScript runtime |
| Manifest | `Data/soccer_player_manifest.json` | Clip list + events + aliases, `look: "realistic"`, `skeleton: "makehuman-52"`, `variants: [v0, v2, v6]` |
| Builder | `Tools/build_soccer_realistic.py` | Reproducible: extracts the three identities from the source, swaps the GAA `kit` material for flat per-club jersey/shorts/socks/boots slots (white PNGs the engine multiplies), retargets the 71 mannequin soccer clips onto the MH skeleton twice (rest-matched for desktop, identity-rest for the browser) |

**Identities:** v0 (clean-shaven), v2 (beard + blue-green eyes), v6 (afro,
brownlight eyes). Desktop picks per character from the stable `CharacterSpec.Id`;
the three sets share one skeleton, one skin and one animation bank — only the
visible mesh toggles. The browser edition ships all three as well (three meshes
per rig, one visible) — this is what costs the 12 MB JSON; gzip on the static
host mitigates most of it.

**Runtime changes:** the C# loader (`SoccerClipRig.cs`) now resolves bones by
MakeHuman names (`thigh_l`, `calf_l`, … — the old `shin_L` lookup never matched,
so foot-planting IK and look-at were silently dead), hides the two unpicked
identity meshes per player, and tints by material **name** so all three
identities follow club colours. Skin, eyes and facial atlases are left natural
(multiply-tinting them would corrupt the baked shading). GDScript
(`ProceduralRig3D.gd`, `BrowserBoot.gd`) validates either skeleton family
(Arena-18 or MakeHuman-52), builds the extra identity meshes sharing the one
skin, poses bones by MH names when present, and recolours every identity mesh.
The foot IK / reach arm bug where the browser looked up `UpperArmR` (never a
real bone name) is fixed as well.

**Verification** (all local, CI re-runs the same):
`Tools/build_soccer_realistic.py` 108,375 tris total; GLB round-trips through a
strict glTF reader (`gltfread`): 52 joints, 71 clips × 53 channels, pelvis
translation present, weights sum to 1, pose ranges sane (idle hips 0.93 m, keeper
dive head at 0.26 m, header apex 1.91 m). `test_soccer_forge.py` **101 passed**
(stdlib python: **99**, motion section needs the venv), `test_pads.py` **129
passed**, GDScript parses via `gdparse` (Godot CI job compiles it for real).

## Limits / next steps

- The browser edition now plays the same baked clips as desktop; the
  procedural gait remains as a fallback when clips are absent.
- The realistic rig ignores `SkinHex`, `HairStyle` etc. — faces come from the
  three shipped identities (v0/v2/v6); extending to more (e.g. v1/v4/v6) is
  "extract more variants", a one-line change in the builder.
- In-game visual check remains user-side: no Godot/.NET in the sandbox, so
  renders/screenshots must come from CI artifacts or the host machine.
- `soccer_rig.json` is **12.1 MB** — heavy; the browser could ship only v0
  (drops ~8 MB) if the transfer cost matters on slow connections.
- Kit detail is flat colours (no fabric weave), matching Arena's per-club kit
  system; the realistic body/face still carries the original MH textures.
- All players share one 1.77 m mesh; the C# loader scales the rig node by
  `CharacterSpec.Height`, so editor height edits still work.
- Editor preview/`rig_default.json` stays the 18-bone procedural rig.
