# Gaelic clip merge

The shipped footballer is `Gaelic_Football_3d/assets/models/gaelic_player.glb` (52 joints, the 32 clips named in `src/main.c`, one mesh per `.parts` line). `forge.py retarget` can put one clip onto `assets/source/makehuman_template.glb`. It does not merge that clip into the squad player.

```
python3 forge.py gaelic-clip check PLAYER.glb --parts gaelic_player.parts --textures assets/textures

python3 forge.py retarget CLIP.fbx assets/source/makehuman_template.glb \
  --root-motion inplace --out /tmp/gf_one_clip.glb

python3 forge.py gaelic-clip merge PLAYER.glb /tmp/gf_one_clip.glb \
  --source CLIP_NAME --name bounce --out /tmp/gf_candidate \
  --retarget-cmd "python3 forge.py retarget CLIP.fbx assets/source/makehuman_template.glb --root-motion inplace --out /tmp/gf_one_clip.glb"
```

The manifest stores relative paths and sha256 identities, the Sprite Forge version, the retarget command you passed, and the measured pelvis travel. It does not invent a licence. Vendor metadata inside an FBX is not permission to redistribute the result. Keep the candidate on the machine that built it until the real author and terms are known. This branch does not contain a merged bounce GLB for that reason. The previous commit on the branch did; that history was not rewritten.

The output cannot be `assets/models/gaelic_player.glb`. An existing candidate needs `--replace`. A name the player already uses (`run`, `jog`, …) needs `--replace-clip`, and the manifest names the clip that was displaced. Keys are rejected when times go backwards, a quaternion is not unit length, or a pelvis translation is not in metres.

`python3 tools/test_gaelic_clip_merge.py` checks the shipped player and merges a synthetic clip (authored by the test) into a temporary copy of the 95-mesh squad.
