# Gaelic clip merge

The shipped footballer is `Gaelic_Football_3d/assets/models/gaelic_player.glb` (52 joints, the 32 clips named in `src/main.c`, one mesh per `.parts` line). `forge.py retarget` can put one clip onto `assets/source/makehuman_template.glb`. It does not merge that clip into the squad player.

```
python3 forge.py gaelic-clip check PLAYER.glb --parts gaelic_player.parts --textures assets/textures

python3 forge.py retarget CLIP.fbx assets/source/makehuman_template.glb \
  --root-motion inplace --out /tmp/gf_one_clip.glb

python3 forge.py gaelic-clip merge PLAYER.glb /tmp/gf_one_clip.glb \
  --source CLIP_NAME --name bounce --out /tmp/gf_candidate \
  --provenance retarget \
  --retarget-cmd "python3 forge.py retarget CLIP.fbx assets/source/makehuman_template.glb --root-motion inplace --out /tmp/gf_one_clip.glb"
```

Paths in the manifest are relative to the repository root (`Gaelic_Football_3d/...`), not to the shell's current directory. A file outside the repo keeps its sha256 and has `"path": null`.

`--provenance authored` is a clip this repo wrote. It has no retarget command. `--provenance retarget` is an external clip: `--retarget-cmd` must be the exact `python ... forge.py retarget ... .fbx` or `.glb` line. That line is stored and is not run again. A sentence is rejected. Leaving provenance unspecified does not claim either source.

The manifest stores sha256 identities, the Sprite Forge version, and the measured pelvis travel. It does not invent a licence. Vendor metadata inside an FBX is not permission to redistribute the result. Keep the candidate on the machine that built it until the real author and terms are known. This branch tip does not contain a merged bounce GLB. The commit merged by pull request 80 still does; that history was not rewritten. These checks do not say anything about how the player runs.

The output cannot be `assets/models/gaelic_player.glb`. An existing candidate needs `--replace`. A name the player already uses (`run`, `jog`, …) needs `--replace-clip`, and the manifest names the clip that was displaced. Keys are rejected when times go backwards, a quaternion is not unit length, or a pelvis translation is not in metres.

`python3 tools/test_gaelic_clip_merge.py` checks the shipped player and merges a synthetic clip (authored by the test) into a temporary copy of the 95-mesh squad.
