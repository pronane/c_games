# Real match motion from our own recordings

These moves come from the team's own Veo match recordings: four matches, 121 highlight clips, adult players in a junior league in Ireland. The team owns the footage and allows its use in Arena FC and Sprite Forge.

**Privacy.** Only joint angles are kept. No video, images, faces, names, shirt numbers or per-player tracks are stored here, in the game or in Sprite Forge. The raw video was deleted after processing.

## How they were made

1. Sprite Forge's match capture (`sforge.matchcapture`, v11.26) ran on a RunPod RTX 4090. It finds the people in each frame (YOLOX), tracks them, estimates their 2D pose (RTMPose Halpe-26) and lifts it to 3D with Sprite Forge's own lifter. That lifter was trained on SkillCorner's MIT pose data.
2. The 3D motion was fitted onto the shared skeleton with the mocap IK (`sforge.jointtrack`). There were two passes, at 15 and 25 fps.
3. `Tools/import_matchcapture.py` kept only the best of about 3,000 raw takes. Each kept take must:
   - pass Sprite Forge's motion checks (`tools/check_motion.py`);
   - be a real run, with both thighs swinging 45°+ and alternating, or a real kick, with a single dominant swing of 55°+;
   - be steady (low joint-angle jitter);
   - have the legs visible;
   - fit well.

   At most one run and two kicks are taken from each clip. Arms are low-passed, because far-camera arms are noisy.

`_import.json` lists every kept take, with its fit error, how visible the legs were, and its estimated speed. It also counts why the rest were rejected.

## Limits

The camera is wide and players are 60–150 px tall, so these moves give real gait timing, lean and weight but not fine detail. Kicks are hard to recover: a swing lasts a few frames, and the 2D detector often mistakes a sprint stride for a kick. Most of what survives is running.
