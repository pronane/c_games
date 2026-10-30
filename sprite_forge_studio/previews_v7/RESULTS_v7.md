# Sprite Forge Studio v7 tests

50 / 50 passed  (linux, Python 3.13.5)

| section | test | result | detail |
|---|---|---|---|
| slots | build --rig sample_stocky (full slots) | PASS | rc=0 |
| slots | model.glb has the 4 core slots | PASS | ['Skin_Mat', 'Jersey_Mat', 'Shorts_Mat', 'Socks_Mat', 'Shoes_Mat', 'Hair_Mat', 'Eye_Mat'] |
| slots | model.fbx has the 4 core slots | PASS | ['Skin_Mat', 'Jersey_Mat', 'Shorts_Mat', 'Socks_Mat', 'Shoes_Mat', 'Hair_Mat', 'Eye_Mat'] |
| slots | core4 -> exactly Skin/Jersey/Shorts/Socks | PASS | ['Skin_Mat', 'Jersey_Mat', 'Shorts_Mat', 'Socks_Mat'] |
| slots | empty core slots kept (upper body only) | PASS | ['Skin_Mat', 'Jersey_Mat', 'Shorts_Mat', 'Socks_Mat'] |
| slots | mannequin GLB slot names | PASS | ['Skin_Mat', 'Jersey_Mat', 'Shorts_Mat', 'Socks_Mat', 'Trim_Mat', 'Shoes_Mat', 'Hair_Mat', 'ball', 'ball_seam', 'Eye_Mat', 'EyeWhite_Mat', 'Mouth_Mat'] |
| anim | anim-export --verify (lanky, 3 moves, +fbx) | PASS | rc=0 |
| anim | base + anim_<move> + manifest files | PASS | ['anim_idle.fbx', 'anim_idle.glb', 'anim_run.fbx', 'anim_run.glb', 'anim_walk.fbx', 'anim_walk.glb', 'character_base.fbx', 'character_base.glb', 'manifest.json' |
| anim | manifest lists 3 moves | PASS | ['format', 'version', 'name', 'fps', 'base', 'base_fbx', 'bones', 'bone_count', 'moves', 'root_motion', 'materials', 'raylib', 'notes'] |
| anim | topo_sorted puts parents first | PASS | re-ordered=True |
| anim | re-order keeps the pose | PASS |  |
| anim | raylib names <=31 bytes, unique | PASS | max 23 bytes |
| anim | build --anim-export -> out/anim/ | PASS | rc=0 |
| clean | dedupe drops Body.001 + Body_LOD1 | PASS | ['Body.001', 'Body_LOD1'] |
| clean | different parts kept | PASS |  |
| clean | Z-up cm GLB -> +Y up | PASS | up=[0. 1. 0.] |
| clean | -> metres (height ~ original) | PASS | h=1.631 m |
| clean | -> grounded (min y = 0) | PASS | 0.0 |
| clean | clips upright too | PASS | idle |
| tmpl | unreal bone names detected | PASS | 22 mapped bones |
| tmpl | unity bone names detected | PASS | 22 mapped bones |
| tmpl | mixamo bone names detected (Meshy zip) | PASS | 22 mapped bones |
| tmpl | meshy-paid asset refused in a pack | PASS |  |
| tmpl | build with the UE5-named rig | PASS | rc=0 |
| equip | build with 2 outfits + 2 props | PASS | rc=0 |
| equip | outfit + prop materials in model.glb | PASS | ['Skin_Mat', 'Jersey_Mat', 'Shorts_Mat', 'Socks_Mat', 'Shoes_Mat', 'Hair_Mat', 'Eye_Mat', 'Armour_Mat', 'Prop_sample_sword_Grip', 'Prop_sample_sword_Guard', 'Pr |
| equip | build_report has equip licences | PASS |  |
| equip | mannequin + prop -> library rig | PASS | rc=0 |
| equip | parse_outfit aliases (foot->feet) | PASS | {'name': 'x', 'hide': ['feet', 'arms']} |
| equip | unknown hide region rejected | PASS |  |
| human | build male game_engine | PASS | 65 bones 13380 verts 0.13s |
| human | skeleton default | PASS | 163 |
| human | skeleton default_no_toes | PASS | 135 |
| human | skeleton body | PASS | 26 |
| human | height parameter monotonic | PASS | [1.292 1.659 2.382] |
| human | female shorter than male (default) | PASS | 1.590 / 1.730 |
| human | forge.py human -> library rig | PASS | rc=0 |
| human | build --human | PASS | rc=0 |
| human | no assets -> clear message, rc 3 | PASS | rc=3 |
| human | build --human fallback (mannequin + warning) | PASS | rc=0 |
| autoskin | sample_lanky re-skinned, walk mean err < 20 mm | PASS | mean 2.7 mm p95 10.9 mm max 26.9 mm, dominant-bone agreement 94.3% |
| autoskin | sample_chibi re-skinned, walk mean err < 20 mm | PASS | mean 5.1 mm p95 16.4 mm max 59.8 mm, dominant-bone agreement 79.8% |
| autoskin | sample_stocky re-skinned, walk mean err < 20 mm | PASS | mean 5.7 mm p95 17.2 mm max 126.8 mm, dominant-bone agreement 74.7% |
| autoskin | CLI: Z-up cm OBJ -> library rig | PASS | rc=0 |
| autoskin | stood up + scaled to skeleton | PASS | 2.005 vs 2.005 m |
| autoskin | build --rig byo_t | PASS | rc=0 |
| cli | forge.py --help lists human/autoskin/anim-export | PASS |  |
| cli | version 7.x | PASS | ['Sprite Forge Studio 7.0.0'] |
| cli | profile with v7 keys validates | PASS | ['   warning: no images/manifests: only the standard outputs (sprites.cfg, atlas.json, character.ini) are written'] |
| cli | doctor runs | PASS |  |
