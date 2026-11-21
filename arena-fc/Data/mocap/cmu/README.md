# CMU motion capture (Arena FC)

19 takes from the **CMU Graphics Lab Motion Capture Database**:

- 6 soccer kicks (subjects 10 and 11);
- 7 running and jogging cycles;
- 4 cuts and turns at running speed;
- 2 sudden stops.

They were imported with `Tools/import_cmu_football.py`, which uses Sprite Forge's BVH importer (BVH, then retarget, then canonical keys). They are baked into `Data/models/soccer_player.glb` as `soccer_mocap_*`, and the motion-matching table selects them.

> The data used in this project was obtained from mocap.cs.cmu.edu.
> The database was created with funding from NSF EIA-0196217.

Licence: free for all uses, including inside commercially sold products. The data may not be resold directly, even in converted form. The BVH conversion is by B. Hahne (cgspeed), mirrored at github.com/meshula/cmu-mocap. `_import.json` records each take and its retarget error.
