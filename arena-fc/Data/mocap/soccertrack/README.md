# Real match motion from SoccerTrack v2 (CC BY 4.0)

126 moves are cut from **SoccerTrack v2** by Atom Scott, Ikuma Uchida, Kento Kuroda, Yufi Kim and Keisuke Fujii (2025). The dataset is licensed **CC BY 4.0**: <https://huggingface.co/datasets/atomscott/soccertrack-v2>.

It contains 10 full university matches filmed as 4K panoramas at 25 fps. Every ball event is labelled with its frame and player.

**Changes made:** the 3D pose was estimated from the video and fitted to the Arena FC skeleton. Only joint angles are kept. No video, images or player identities are stored.

## How they were made

1. Sprite Forge's `tools/soccertrack_capture.py` read every labelled event (pass, lofted pass, cross, shot, free kick, header, tackle, block, drive). The job ran on a RunPod RTX 4090 for about 2.8 h.
2. The dataset's per-frame player positions are approximate, so each one served as a hint. The person detector found the real player on a magnified crop around it (`matchcapture.refine_box`).
3. Each player was posed (RTMPose), lifted to 3D (Sprite Forge's lifter) and fitted with the mocap IK. Kick contact was refined to the ankle-speed peak. Dribbles became stride loops.
4. That gave 3,631 raw moves. `Tools/import_matchcapture.py --source soccertrack` kept the best 126:
   - Each move must pass Sprite Forge's motion checks, show a visible swing, track steadily, show the legs and fit well.
   - There are quotas per kind and per pass type, and at most a few moves per match half.

| kind | moves |
|---|---|
| passes | 45 |
| lofted passes | 20 |
| free kicks | 10 |
| crosses | 6 |
| shots | 1 |
| dribble loops | 24 |
| tackles | 12 |
| blocks | 8 |

`_import.json` lists every kept move with its fit error and leg visibility. It also counts why the rest were rejected.

## Limits

Players are 30–115 px tall in the panorama, and moves are only cut for players at least 60 px tall. That gives real timing and weight but not fine detail. Headers and shots are rare in the labels.
