# Arena FC — Sprite Forge soccer player (mesh + skeleton + animations)

*Current status, 2026-11-18:* **the realistic footballer ships on desktop and in the
browser.** The 18‑bone sculpted "mannequin" was the first answer to the brief and is
kept in git history (`eab13d8`, Sprite Forge **v11.17** rebuild of the v11.13 original —
v11.14–v11.17 only touched the scan‑capture head path, so the sculpt rebuild was
byte‑identical). The step‑change that actually landed is a new build of the game mesh:
a **MakeHuman‑derived, anatomically real footballer on the full 52‑joint skeleton with
all 71 soccer clips**. Player previews rendered from the shipped data:

| Frame | File |
| --- | --- |
| Player, full body, run clip | `media/screenshots/render_player_run.png` |
| Close‑up, run clip | `media/screenshots/render_closeup_run.png` |
| Close‑up, header clip (frame 0) | `media/screenshots/render_closeup_header.png` |
| Broadcast/gameplay view | `media/screenshots/render_gameplay_run.png` |

CPU‑rasterised from `Data/soccer_rig.json` by `Tools/render_gameplay.py` (not a capture of
the running build; the sky‑coloured triangles at the pitch edges are that tool's known
coverage artifact, not a model defect).

## What ships now (Option 2 — the realistic player)

| Artifact | Path | What it is |
| --- | --- | --- |
| Realistic GLB | `Data/models/soccer_player.glb` (12.8 MB) | MakeHuman‑derived footballer: real anatomy, baked skin/eye/hair atlases, smooth normals, **52‑joint skeleton incl. fingers, ball‑of‑foot, neck**. 108,375 tris across 3 identities sharing one skin, **71 animation clips × 53 channels** |
| Browser rig | `Data/soccer_rig.json` (12.1 MB) | The same player in the GDScript rig schema (31,101 verts / 36,934 tris base "v0" + `variant_sets` v2 36,805 tris / v6 34,636 tris), all 71 clips baked |
| Manifest | `Data/soccer_player_manifest.json` | Clip list + loop flags + `ball_contact` events + 82 aliases; `look: "realistic"`, `skeleton: "makehuman-52"`, `variants: [v0, v2, v6]` |
| Builder | `Tools/build_soccer_realistic.py` | Reproducible (see pipeline below); regenerates all three artifacts in ~20 s |
| Tests | `Tools/test_soccer_forge.py` | 101 checks (stdlib): GLB round‑trip (52 joints, 71 clips, MASK only on hair/brows/lashes/beard, weight sums = 1, tri budget 100k–115k) + browser JSON schema gates + manifest gates |

**Identities (3 looks, like the GAA squad):**

| Id | Look | Eyes | Hair / face |
| --- | --- | --- | --- |
| v0 | clean‑shaven base | brown | short02, brown brows |
| v2 | bearded veteran | blue‑green | short01, beard shell + facial hair |
| v6 | afro | brownlight | afro01, darker brows |

Desktop picks an identity per character from the stable **display name** (same roster →
same faces across runs; `SoccerClipRig.ApplyVariant` with the same `h*31+c` hash style the
browser uses). The browser edition assigns v0/v2/v6 per slot (`(side*5+i) % 3`). All three
identities are hidden/shown at runtime, so players on one pitch visibly differ.

## Pipeline

1. **Extract** the v0/v2/v6 identities from `Gaelic_Football_3d/assets/models/gaelic_player.glb`
   (52 joints, JOINTS_0/WEIGHTS_0, 4 influences per vertex).
2. **Kit swap** — the source's GAA `kit` material is replaced with flat white slots
   (`jersey`/`shorts`/`socks`/`boots`) that the engines multiply by club colours; skin,
   eyes, brows, lashes, hair and beard are kept untouched (multiply‑tinting baked atlases
   would wreck them). The GAA kit texture itself is **not** carried over.
3. **Retarget** — the 71 mannequin soccer clips (`Tools/soccer_motions.py`) are
   retargeted onto the MH skeleton twice: rest‑matched for the desktop GLB, and against an
   identity rest for the browser JSON (the GDScript runtime sets pose rotations directly).
4. **Export** — GLB via `sforge.glbpack`, browser JSON in the `rig_default.json` schema
   (`bones[{n, p, h}]` parents‑first, `pos/nrm/uv/bi/w/idx/mats`, baked clip keyframes
   with fps 30 and ball‑contact events), manifest JSON.

## Runtime changes

- **Desktop (C#)** — `SoccerClipRig.cs`: bone names are MakeHuman (`thigh_l`, `calf_l`,
  `upperarm_l`…). The old lookups (`shin_L`, `upperarm_L`) could never match, so
  foot‑planting IK and ball look‑at had silently never run. Two unpicked identity meshes
  per player are hidden at spawn; kit tint is driven by glTF **material name**
  (`skin_v*`/`eyes_*` stay natural, everything else tints per club) with a
  `resource_name`→sub‑resource‑path fallback.
- **Browser (GDScript)** — `ProceduralRig3D.gd` validates either skeleton family
  (Arena‑18 or MakeHuman‑52), builds the v2/v6 identity meshes sharing the one skin, and
  reports the GLB match by MH names. `BrowserBoot.gd` resolves Arena‑style names onto MH
  names (`bname()`/`MH_MAP` — including the `UpperArmR`→`upperarm_r` path that could never
  resolve, and the root‑translation clip lookup), recolours every identity mesh, hides the
  two unused ones, and keeps the clip system (cadence matching, hysteresis, one‑shots,
  lean/roll) unchanged.
- The realistic rig ignores the 18‑bone‑era editor fields (`SkinHex`, `HairStyle`…).
  **Editor preview stays the 18‑bone procedural rig** (`rig_default.json`) — it is the
  rig the editor's bone list and skeleton overlay were built around.

## Licence / asset provenance

- The realistic body/anatomy/textures derive from **MakeHuman assets (CC0)** via the
  Gaelic squad build (`sprite_forge/tools/gaelic_squad.py`); MakeHuman's CC0 licence
  places no restrictions on shipping the derived meshes.
- Source file `Gaelic_Football_3d/assets/models/gaelic_player.glb` is this repository's
  own sanitised build. It contains **no GAA branding** (kit textures were swapped for
  flat per‑club slots in this build) and **no Mixamo data**: the 71 clips come from
  Sprite Forge's mannequin mocap‑free pose library in this repo (`Tools/soccer_motions.py`),
  and the `.fbx` caveat documented for the Gaelic project (`Gaelic_Football_3d/README.md`)
  is unaffected.
- The Sprite Forge pipeline itself, the sculpt, the retarget and the exports are original
  to this repository. No FIFA/PES/eFootball assets, likenesses, kits or branding are used.
- If you redistribute, keep an attribution note for MakeHuman (courtesy; CC0 does not
  require it).

## Verification

| Check | Result |
| --- | --- |
| GLB round‑trip via `sforge.gltfread` | 52 joints parents‑first; 71 clips × 53 channels; pelvis translation present; MASK + `doubleSided` only on hair/brows/lashes/beard/facial; weights sum to 1.0 |
| Pose sanity (from GLB) | idle hips 0.935 m; keeper‑dive head ≈ 0.26 m; header apex ≈ 1.91 m |
| `test_soccer_forge.py` | **101 passed, 0 failed** (identical under system python — earlier motion mismatch fixed by the manifest/GLB gate rewrite) |
| `test_pads.py` | **129 passed, 0 failed** |
| `gdparse` (BrowserBoot, ProceduralRig3D) | parses clean; `gdlint` shows **zero new** violations vs baseline (164 → 76, all identical categories) |
| CPU render of shipped data | 4 preview frames (see top of file) show correct anatomy, stance, gait and broadcast view |
| CI (`.github/workflows/arena-fc-tests.yml`) | gd‑tests + `dotnet` build + `test_soccer_forge.py` + `test_pads.py` re‑run; forge section (numpy) runs only where numpy exists by design |

## History

- **2026‑11‑18 (this branch, `f138585`+)** — realistic player lands (Option 2).
  Option 1 (the v11.17 sculpted‑mannequin rebuild, `eab13d8`) proved byte‑identical and
  established the test/lint baseline; it remains in history but no longer ships.
- **2026‑11‑17** — original Sprite Forge v11.13 footballer (PR #100, `891facd`), 18 bones,
  16,000 tris, 67→71 clips.
- v2 online (27 Oct 2026): reconnect, host migration, rollback prediction.

## Limits / next steps

- **Browser payload**: `soccer_rig.json` is **12.1 MB** (three identities × baked clips).
  Mitigations in place: static hosts gzip it well (~70% smaller over the wire), and only one
  identity per player is visible. If transfer cost matters, ship `v0` only (drops ~8 MB,
  one‑line builder change) at the cost of uniform faces. Accepted knowingly by selecting
  the browser+realistic combination; flag it if you want the v0‑only cut instead.
- **Visual/animation check on the real engine remains user‑side**: no Godot/.NET in the
  sandbox. The CI Godot job compiles the GDScript; the previews above are CPU renders of
  the shipped data, not engine captures.
- The realistic rig has no per‑player face editor (three fixed identities); more looks =
  extract more variants in the builder (source ships nine).
- All players share one 1.77 m mesh; `SoccerClipRig` scales by `CharacterSpec.Height`, so
  editor height edits still work.
- Editor preview/`rig_default.json` stays the 18‑bone procedural rig.
- `Data/soccer_player.glb` embeds no textures on kit slots beyond the flat whites —
  intentional (per‑club tint), matching the flat‑kit approach everywhere else in Arena FC.
