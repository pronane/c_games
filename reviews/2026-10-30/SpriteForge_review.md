# Sprite Forge — review and improvements (front-photo puppet)

**Scope:** `sprite_forge/` (~30k lines of Python). I concentrated on the path you asked about: one front image to an HD sprite sheet with realistic moves (`sforge/puppet.py`, `build.py::_puppet_photo`). I skimmed the rest (library, FBX/GLB, scan, GUI, plugins) and did not review or test it.

## How I tested (and the limits)
- **Test input:** a front-facing render of the project's own mannequin (not a real photo), with the 33 pose landmarks placed **by hand**. The pose model (`pose_landmarker_full.task`) is not installed and I had no network, so automatic landmark detection was not exercised.
- **Not tested:** real photographs, cartoon characters, the `--turn` side/back views, faces/expressions (`--expressions off`), and the GUI.
- **Regression suites** (run on the patched code): `test_v9.py` 44 tests, 0 failed; `test_v8.py` 6 tests, 0 failed (some skipped for missing tkinter / pose model). `test_v7.py` scored 9/22 on both the patched **and** the original code in my sandbox because I did not extract the binary library assets, so I treat it as inconclusive, not a pass.

## What the puppet does today
The cut-out is split into torso, upper arm, forearm, thigh and shin pieces; each move is a list of key poses; every frame rotates the pieces about shoulder, elbow, hip and knee. Interpolation between keys is linear.

## What I changed (opt-in, defaults unchanged)
| Option | What it does | Evidence |
|---|---|---|
| `--puppet-engine skin` | Limbs bend smoothly (linear blend skinning, premultiplied-alpha splatting) instead of rigid tubes with cap discs. | Real `forge.py build`, 8 moves: separate pixel islands per frame fell from 3.1 to 2.0 (kick), 2.3 to 2.0 (punch), 2.6 to 2.0 (jump). See `sprite_forge_classic_vs_skin.png` (classic above, skin below). Build time 7.1 s vs 9.3 s. |
| `--motion-style polish` | Smooth (PCHIP) in-betweens, slight lag on forearms/shins, small sway and landing squash. | Velocity change at key poses (deg/frame): kick 15.4 to 6.2, throw 8.7 to 4.2, punch 1.4 to 0.6. Changes kick, throw, hit, taunt and both specials in the stock fighter14 preset. **Cost:** peak joint speed rises (kick roughly 105 to 152 deg/frame). I have not judged it by eye in motion; check before making it the default. |

Hidden-hand builds (where a hand is copied from the other one) fall back to the classic renderer. Supersampling (`SkinRig.SS = 2`) exists in code, but I measured it about 6x slower in an earlier run and did not wire a flag for it.

I also suspected a dark fringe from Pillow's resampling and measured it: the effect is about 1.8/255, so I did not change the classic path.

## Visible limits that remain
- **A front photo has no depth.** Punches and kicks that should come toward the camera extend sideways instead (see the punch rows). For a side-on fighting game, use the existing `--turn 90` side-on estimate, which I did not test.
- **Guard and fist poses** still look stiff: the pieces are 2D cut-outs, so there is no foreshortening.
- **Landmarks drive everything.** Cartoon or non-human characters (like the Mango Mo example) will not be detected by a human pose model; a landmark editor or a proportion template would help.

## Suggested next steps
1. Run `--puppet-engine skin` on real photos and cartoon art and compare; tune the weight widths (`1.3 * R`, `1.9 * R`) per limb.
2. Upscale the cut-out 2x before rigging when targeting HD cells, so rotated pieces stay sharp.
3. Foot-lock for photo builds (it currently covers mannequin/library moves only) to stop sliding in walk.
4. Judge `polish` by eye on kick/throw; reduce lag or clamp peak speed if it looks floaty.
5. Add the skin engine to `tools/test_v9.py` (one build, island-count and clipping assertions).
6. Fix the sample code path: `forge.py cutout` needs the pose model; document `tools/setup_pose.py` in the README quick start.

## Files
`sprite_forge_v9.1_patch.zip` contains `sforge/skinwarp.py` and `sforge/motionpolish.py` (new), plus patched `forge.py` and `sforge/build.py` with a unified diff (`forge_and_build.diff`).
