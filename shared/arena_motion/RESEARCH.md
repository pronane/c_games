# Motion reference research

The shared C core is inspired by the approach used in Arena FC; it is not a
copy of that game or an ML model. This file records external reference material
reviewed to guide further work. External code and data are not bundled here.

- [Motion Matching & Code vs Data Driven Displacement](https://github.com/orangeduck/Motion-Matching),
  Daniel Holden, commit `57b7250e0d34a4e456a34d47e24c2f05fdcc711e`.
  The example **code** is MIT licensed. It demonstrates inertial transitions,
  contact and trajectory matching. Its example data and trained assets have
  separate provenance: its README identifies LaFAN1 as CC BY-NC-ND 4.0. Do not
  assume the code licence permits commercial distribution or training on that
  dataset. An archive was inspected locally; no third-party code, animation data
  or pretrained model was added to the game or shared library. The simple
  exponential contact-weight smoothing in this repo is independently written,
  not a learned model or the reference's full inertialization system.
- [SoccerTrack v2](https://github.com/AtomScott/SoccerTrack-v2), commit
  `a752d294df2a0e816e827b70f284980698f5a50e`: its code is MIT and the authors
  state its videos and annotations are CC BY 4.0. The licence and a small
  pitch-keypoint correction file were inspected locally, but match footage is
  hosted on Hugging Face / Google Drive, which were not accessible from this
  sandbox. Its annotations provide 2D match tracking, not rigged 3D gait, so
  they cannot be directly used as a motion-matching animation database. Respect
  attribution, consent and licence conditions before using any data.
- [LaFAN1](https://github.com/ubisoft/ubisoft-laforge-animation-dataset) and
  [Bandai Namco motion datasets](https://github.com/BandaiNamcoResearchInc/Bandai-Namco-Research-Motiondataset)
  are marked non-commercial (LaFAN1 also no-derivatives). They are useful to
  study, but are not cleared here for a commercial game or trained assets.

No model has been trained or retargeted from these sources. Authentic trajectory
matching needs clips with usable root motion, rig compatibility, contacts and
clear rights. Review each individual asset's terms before download, training,
conversion, sharing or game distribution. Capture original or appropriately
licensed Gaelic actions where possible.

## CMU locomotion experiment

The [CMU Graphics Lab Motion Capture Database](http://mocap.cs.cmu.edu/) says
its data may be used in research and commercially sold products, but may not be
resold directly, including in converted form. It requests acknowledgment of the
source and NSF funding. CMU also warns that hand/toe joints are noisy and that
finger and thumb motions were not captured. CMU footage is therefore not a fix
for ball grip or Gaelic-specific skills.

Four cgspeed-converted BVHs (`16_35`, `16_36`, `09_01`, `09_02`) were retrieved
from the `meshula/cmu-mocap` mirror at commit
`09a07f54f3bbb58797325f009282d0b2048a2871` and inspected locally. Sprite Forge
projected them onto its canonical skeleton and selected tentative cycles; this
is a retarget approximation, not validation of anatomical fidelity. No BVH,
retargeted motion, generated player or external model weights are committed.

For a controlled comparison, `Gaelic_Football_3d/tools/build_cmu_jog_candidate.py`
checks the SHA-256 of `16_35`, imports it, retargets it to the player template,
strips horizontal root motion, and merges it into a **local copy** replacing
`jog`. It writes a provenance record; the shipped player is untouched. The
candidate passed the numerical model tests, but is not validated visually and
is not a new training dataset or a replacement for Gaelic-specific motion.
The visual workflow generates the candidate on the runner and records both the
original and candidate with the same scripted inputs. Check cycle transitions,
foot sliding, all body parts and rights before deciding whether to ship it.
