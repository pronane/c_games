# Gaelic clip merge

The shipped footballer is `Gaelic_Football_3d/assets/models/gaelic_player.glb`: 52 joints, the 32 clips named in `src/main.c` `CLIP_NAMES`, and one mesh per line of `gaelic_player.parts`. Kit textures are a split atlas (left half jersey, socks and boots; right half shorts). Sprite Forge's mannequin is a different skeleton. `forge.py retarget` can put one FBX clip onto `assets/source/makehuman_template.glb`. It does not merge that clip into the squad player, and it drops fingers, twist bones and the face that the template does not share.

`forge.py gaelic-clip` is the missing step. It checks the player, or copies one named clip onto a **new** GLB by bone name. It does not rewrite meshes, skin weights, materials or the other clips, and it will not write over the file it read.

```
python3 forge.py gaelic-clip check \
  ../Gaelic_Football_3d/assets/models/gaelic_player.glb \
  --parts ../Gaelic_Football_3d/assets/models/gaelic_player.parts \
  --textures ../Gaelic_Football_3d/assets/textures

python3 forge.py retarget CANDIDATE.fbx \
  ../Gaelic_Football_3d/assets/source/makehuman_template.glb \
  --root-motion inplace --out /tmp/gf_one_clip.glb

python3 forge.py gaelic-clip merge \
  ../Gaelic_Football_3d/assets/models/gaelic_player.glb /tmp/gf_one_clip.glb \
  --source CLIP_NAME --name bounce \
  --parts ../Gaelic_Football_3d/assets/models/gaelic_player.parts \
  --out /tmp/gf_candidate
```

The candidate directory holds `gaelic_player.glb`, a copy of `.parts`, and `manifest.json`. The game keeps loading the canonical GLB. Point `--model` at the candidate to try it. Do not run `gaelic_squad.py --install` or `gaelic_forge.py --install` as part of this. Those replace the squad.

There is no photo-to-Gaelic command. Reference pictures are pose guides, not model files, and they are not assets. The manifest does not invent a licence: record the clip's real author and terms before anyone redistributes it.

`python3 tools/test_gaelic_clip_merge.py` checks the shipped player and a template merge.
