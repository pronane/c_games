# Real in-match motion: SkillCorner open body pose

These 56 moves come from two A-League 2024/25 matches: Brisbane Roar v Perth Glory and Sydney FC v Adelaide United.

- **Pose:** [SkillCorner Open Data — Body Pose](https://huggingface.co/datasets/SkillCorner/opendata-bodypose), 29 3D joints at 25 fps estimated from the broadcast video.
- **Events:** the same matches' dynamic events from [SkillCorner Open Data](https://github.com/SkillCorner/opendata).
- **Licence:** MIT for both. Credit: SkillCorner (with PySport).

`Tools/import_skillcorner_pose.py` builds them in five steps:

1. Cuts each player's joints around every shot, pass, lofted pass, clearance, first touch, ball win and carry.
2. Keeps the cleanest takes: complete, detected throughout, lowest joint error, and at most two per player per kind.
3. Finds the contact frame and kicking foot from the ankle-speed peak.
4. Fits each take onto the shared skeleton with Sprite Forge's `sforge.jointtrack`.
5. Cuts each carry to its best two-stride loop.

The fits average 1.4–2.6° of bone error. `_import.json` lists every take with its source event, player, contact point, foot, root velocity and fit quality.

Precision is that of broadcast pose estimation, 7–15 cm per joint, so these clips give the timing, posture and weight of real football rather than fine detail. Feet are planted by the game.
