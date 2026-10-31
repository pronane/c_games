# Hurling 3D: rigged hurler assets (first pass)

A hurling counterpart to `Gaelic_Football_3d`. So far this folder holds the **art and motion assets only**, not a game.

Regenerate with `python3 tools/gen_hurling_assets.py assets --sheet` (needs numpy and Pillow).

| File | What |
|---|---|
| `assets/hurler_home.glb`, `hurler_away.glb` | skinned hurler (690 verts, 1276 tris): helmet with faceguard, glove, kit colours as vertex colours, hurley skinned to its own `hurley` joint. 18 joints, 16 animations at 30 fps. |
| `assets/sliotar.glb` | sliotar, 7.3 cm, with the raised seam. Attach it to the `hurley` joint for solo-running, or to a hand joint. |
| `assets/clips.json` | clip names, lengths, loop flags and the **contact time** in seconds for each strike (use it as the release time, like `game_set_action_timing` in the football game). |
| `assets/clip_*.png` | contact sheets (6 frames per clip) rendered by the generator, so you can check the motion without a game. |

Clips: `idle`, `jog`, `sprint`, `solo_run` (hurley out front, ball balanced on the bas), `strike_overhead`, `strike_ground`, `puckout`, `pickup_flick` (rolling lift), `handpass`, `catch_high`, `block_hook`, `shoulder_charge`, `hit_react`, `knocked_down`, `get_up`, `celebrate`.

In two-handed clips the left hand is solved onto the handle with 2-bone IK at bake time, so the grip stays on the stick through the swing.

## Checked
- Each glb was parsed back: sizes, accessor bounds, index range, weights sum to 1, joint indices, sampler lengths. `gltf-validator` was **not** run (it needs a download).
- Motion was checked by software-rendering the skinned frames (the `clip_*.png`). It has **not** been loaded in raylib or Blender here.

## Limits (be honest about realism)
- The motion is **hand-keyed poses with smooth interpolation**, not motion capture. It reads as the right action and timing, but it is stiffer than the Mixamo clips used in the football game. For true realism, record or buy real hurling mocap, retarget it to this skeleton (names are in `clips.json`), and keep these clips as placeholders.
- The body is low-poly built from tapered tubes. For a final look, replace the mesh but keep the joint names and the generator's keys.
- The rig is **not** the 52-bone Mixamo rig the football game's GPU skinning path expects; a hurling game loads these files with their own 18-bone skin. No separate goalkeeper clips yet beyond `puckout`.
- Not done: the game itself (sliotar physics, the H-shaped goal, 1 point over / 3 under the bar, 15-a-side, hand pass and striking rules). The football engine would need the two-input refactor from `Gaelic_Football_3d/ANALYSIS_2026-10-31.md` first.
