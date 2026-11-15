# Fit a mesh onto the Gaelic skeleton

`forge.py gaelic-fit` skins a GLB or OBJ you already have onto the 52-joint skeleton in `Gaelic_Football_3d/assets/source/makehuman_template.glb`. That file has the same rest pose, the same joint order, the same inverse binds and the same 32 clip bytes as `assets/models/gaelic_player.glb`. The command writes a scratch directory. It does not modify the shipped player, the `.parts` file, or `assets/textures/kit_*.png`, and it refuses to write into `assets/models` or `assets/textures`.

```
python3 forge.py gaelic-clip check Gaelic_Football_3d/assets/models/gaelic_player.glb \
  --parts Gaelic_Football_3d/assets/models/gaelic_player.parts \
  --textures Gaelic_Football_3d/assets/textures

python3 forge.py gaelic-fit MESH.glb --out /tmp/gf_fit

python3 forge.py gaelic-fit MESH.obj --out /tmp/gf_fit --preview --replace
```

Run those from `sprite_forge/` (or pass a path to `sprite_forge/forge.py`). `--out` is a directory:

* `fitted.glb` — one skinned mesh, the template skeleton, all 32 clips
* `fitted.parts` — one row, `0 0 body`
* `manifest.json` — sha256 of the mesh and the template, the exact command, repo-relative paths when the file is inside the repo, weight stats, and a deformation check
* `preview/deform_sheet.png` — only with `--preview`

A second write into the same directory needs `--replace`. The game loads a candidate without installing it, from the `Gaelic_Football_3d` directory:

```
./gaelic_football --model /tmp/gf_fit/fitted.glb
./gaelic_football --model /tmp/gf_fit/fitted.glb --cpu-skin
```

There is a checked-in fixture, a box person built by this repo (no photograph):

```
python3 forge.py gaelic-fit testdata/gaelic_fit_humanoid.obj --out /tmp/gf_fit_box
```

## What the fit does

1. Reads the mesh with the library importer and `orient=auto` (the same pass as `forge.py library add --orient auto`): metres, +Y up, facing +Z when a skeleton maps, feet grounded. An unrigged mesh whose arm span is wider than its height is stood back up afterwards; the longest-axis rule would otherwise treat the arms as the height.
2. Classifies the arms. A T-pose (out to the sides), an A-pose (down, still out from the body) and arms hanging down are warped onto the template's bent A-pose. A raised arm, hands in front of the chest, or a bent knee is refused, and the message says which.
3. Copies skin weights from the nearest point on the template body. The point's barycentric weights are smoothed over the new mesh, then kept to at most 4 influences that sum to 1, in the template's 52-joint order.
4. Packs with `sforge.glbpack.pack`, which keeps the skeleton, the inverse binds and every clip byte.

`pelvis`, `foot_l`, `foot_r`, `hand_l`, `hand_r` and `head` stay in that joint list. The bone count stays 52, under the game's limit of 64.

## Kit atlas and `.parts`

The squad file `gaelic_player.parts` has many meshes per look. Roles are `body`, `kit`, `hair`, `brows`, `lashes`, `eyes`. The game puts `kit_*.png` only on meshes tagged `kit`. Each atlas is split: the left half is jersey, socks and boots, the right half is shorts.

`fitted.parts` tags the single mesh as `body`, so the embedded texture is what you see. A Meshy or Rodin full-body texture does not line up with that split atlas, and this command does not rebuild one. Team colours will not swap. Hair, eyes, brows and lashes are not split out of the source mesh.

## Make the mesh in Meshy or Rodin

This repository does not call Meshy or Rodin, and it does not generate an image of a person. Run the prompt below yourself, in the tool you have a licence for. Use a text prompt. Do not upload a photograph of a real person, and do not upload the private reference images in this project.

Prompt (T-pose, the easier one for this fitter):

```
Full body of a generic adult Gaelic footballer, standing in a strict T-pose,
arms straight out to the sides parallel to the ground, palms down, legs straight,
feet a shoulder width apart, facing the camera. Plain jersey and shorts, no logos,
no text, no number, no helmet. Neutral face, short hair close to the head.
Even studio lighting, no background. Not a real person. No photograph. No celebrity.
```

A-pose, if the tool will not hold a T-pose:

```
Same generic adult footballer, full body, A-pose: arms down about 30 to 45 degrees
from horizontal, still clear of the torso, palms facing the body, legs straight.
Same plain kit, no logos, no text. Not a real person.
```

Multi-view, only if you are driving an image-to-3D model. Generate or draw the views yourself from the prompt above. Every view is the same generic character, the same pose, full body, feet in frame:

* front
* left side
* right side
* back

Do not mix a T-pose front with an A-pose side. Do not use a photo of a real player.

Export:

* Format: glTF binary (`.glb`) or OBJ, with UVs and normals
* Up axis: Y, if the exporter asks. Facing +Z matches the template; the fitter also turns a mesh that faces the other way when the feet show which way is forward
* Pose in the file: the bind pose, not an animation frame
* Polygon budget: about 22 000 triangles. That is the budget `tools/gaelic_forge.py --tris 22000` uses so a squad of these meshes stays comfortable on a laptop. A mesh far above that still fits, and the manifest's `poly_warning` is set past 22 000 triangles
* No extra props in the hands. A ball, a stick, or a cape becomes part of the skin and will stretch

Then:

```
python3 forge.py gaelic-fit ~/Exports/footballer.glb --out /tmp/gf_fit --preview
```

Read `manifest.json`. `deform_flags` lists clips where the body collapsed or a vertex left its bone. The preview sheet is a software skin of idle, run, kick_run, catch and solo, front and side. It is not the game window.

## Gaps

* Fingers follow the nearest hand surface. A fist, a spread hand, or long fingers will not match the template grip.
* Loose clothing, hair, a skirt, or a prop is weighted to the nearest body and can candy-wrap.
* The face is not retargeted. It rides with the head bone.
* One embedded texture. The squad kit atlas is not applied.
* The mesh is scaled to the template height, about 1.74 m. Limb lengths are only approximately matched.
* Poses other than a standing T-pose, A-pose, or arms-down stance are refused.

The manifest does not invent a licence for the source mesh. Keep the candidate on the machine that built it until the author and the terms are known. The template skeleton and clips are the repository's CC0 MakeHuman player.
