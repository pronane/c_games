# Sprite Forge Studio v9 tests

| result | test | detail | s |
|---|---|---|---|
| PASS | expressions: 7 faces, auto per-move map, user map, blink | {'idle': 'neutral', 'punch': 'angry', 'hit': 'hurt', 'taunt': 'taunt', 'victory': 'happy', 'special1': 'shout'} | 0.0 |
| PASS | talk: letters -> mouth shapes (M=mbp, A=ai, O=o, F=fv) | [["mbp", 1], ["ai", 2], ["mbp", 1], ["rest", 1], ["o", 2], ["fv", 1], ["rest", 1], ["e", 2], ["o", 2 | 0.0 |
| PASS | photo expressions: procedural warp of the drawn face only (estimated) | {'happy': 501, 'angry': 418, 'hurt': 697, 'shout': 1004, 'taunt': 266, 'blink': 277} | 0.29 |
| PASS | recolour: sets, region + overlay parsing | 20 sets | 0.0 |
| PASS | recolour: applied to the 3D spec (exact slot colours) | top_colour=#1c3fb0 | 0.0 |
| PASS | recolour: palette swap keeps shading, leaves other colours | red share 1.00 | 0.1 |
| PASS | variants: same seed = same variant, vary limits what changes | seeded + vary=colours keeps body/outfit | 0.0 |
| PASS | foot lock: 2-bone IK removes planted-foot slide | walk slide 7.26 -> 0.28 cm | 0.01 |
| PASS | fx: outline / cel / pixel-art / lighting passes | outline grows, cel 2 colours, pixel blocks, light changes | 0.0 |
| PASS | maps: normal map faces out of the silhouette, emissive picks glow colours | n centre [128 128 255] left [ 26 128 204] right [229 128 204] | 0.0 |
| PASS | blend: parse + crossfade | [('idle', 'walk', 3), ('punch', 'idle', 3)] | 0.0 |
| PASS | physics: ponytail / cape / scarf chains swing | 4 chains (hair_tail,cape,scarf_R,scarf_L), tip moves 0.040 | 0.06 |
| PASS | npc pack: 17 fictional characters | 17 characters | 0.0 |
| PASS | build: mannequin with every v9 option | Done in 3.2s -> /tmp/sfs_v9test_88vzs8q0/b/hero | 3.32 |
| PASS | build: faces.png + per-move expressions noted |  | 0.0 |
| PASS | build: talk strip + 8 mouth shapes + timing |  | 0.0 |
| PASS | build: colours noted as exact for 3D |  | 0.0 |
| PASS | build: variants sheet + 4 variant specs |  | 0.0 |
| PASS | build: blend_idle_walk move made |  | 0.0 |
| PASS | build: footlock slide numbers reported | ['NOTE: footlock: planted-foot slide (mean) idle 0.6->0.0 cm, walk 14.0->0.0 cm, punch 6.1->0.0 cm, hit 0.1->0.0 cm, taunt 4.4->0.2 cm, victory 3.0->0.5 cm, ble | 0.0 |
| PASS | frame data: punch has hit boxes in its active frames, blend is not an attack | punch startup 3 active 2 recovery 1 | 0.0 |
| PASS | maps: maps/atlas_normal.png + atlas_emissive.png |  | 0.0 |
| PASS | LODs: fewer triangles per level, baked model has 1 material | [6236, 3124, 1837] | 0.0 |
| PASS | QA: report written for the build |  | 0.0 |
| PASS | expressions with a beard and a moustache (facial hair follows the face) | uin     2 frames 
  taunt                    mannequin     2 frames 
  [1.23s] faces
  [0.02s] qa
Done in 1.3s -> /tmp/sfs_v9test_88vzs8q0/beard/tash
 | 2.89 |
| PASS | regression: --footlock is part of the render cache key | footlock changes the cached render | 2.9 |
| PASS | build --npc wizard |  | 1.57 |
| PASS | forge.py recolor <folder> --set team_red | recoloured 68 images -> /tmp/sfs_v9test_88vzs8q0/hero_red | 1.13 |
| PASS | forge.py variants --npc goblin -n 6 |  | 0.28 |
| PASS | forge.py atlas: 2 characters, one pack | atlas pack: 2 characters, 52 frames (47 unique) -> 1 page(s) 796x790, fill 84%, 38% of the untrimmed pixels | 0.49 |
| PASS | atlas: rects inside pages, no overlaps, fill > 60% | fill 0.84, 1 pages | 0.0 |
| PASS | forge.py qa <build folder> runs | blend_idle_walk        PASS | 0.23 |
| PASS | QA: an emptied frame is flagged FAIL (exit 1) | hit                    PASS | 0.17 |
| PASS | forge.py framedata <folder> (cast counts as an attack) |  | 0.19 |
| PASS | forge.py npc lists |  | 0.09 |
| PASS | forge.py sets lists |  | 0.1 |
| PASS | forge.py expressions lists |  | 0.1 |
| PASS | forge.py batch: 3-job queue, 2 workers, dependent qa job | Sprite Forge batch queue.txt: 3 ok, 0 failed, 0 skipped in 1.8s (2 workers) | 1.87 |
| PASS | photo regions: shading / faded denim keep their region (not trim / socks) | shaded top: top 0.97 trim 0.00; faded jeans: bottom 0.85 socks 0.00 | 0.05 |
| PASS | recoloured photo: rig pieces come from the pre-recolour colours (forearm kept) | hidden forearm px: original 2053, light-blue top with colour_ref 2053 (without: 0) | 1.6 |
| PASS | forge.py variants --cutout (landmarks.json dict) + photo variants keep the hair | rc 0, photo variants never recolour hair: True | 0.81 |
| PASS | Studio: Style + Extras settings -> forge.py flags | --expr-map punch=shout --no-blink --talk Hi --recolor kerry;hair=#111111 --overlay top:hoops:#ffffff --variants 6 --vari | 0.0 |
| PASS | Studio: defaults add no v9 flags (v8 commands unchanged) | defaults add no flags | 0.0 |
| PASS | Studio: settings -> BuildConfig (in-process build) | recolor/variant/footlock/npc | 0.0 |
| PASS | Godot plugin: import build -> SpriteFrames (all moves) + scene | SFANIMS 7 | 5.85 |
| PASS | Unity package: compiles against stub UnityEngine/UnityEditor APIs | ['    0 Warning(s)', '    0 Error(s)'] | 2.27 |
