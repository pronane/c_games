# 3D asset pipeline — Blender (bpy)

Every model in Aussie Rules 3D is authored programmatically with **Blender**
(the `bpy` module — Blender 4.5 LTS as a Python library) and exported to
glTF binary (`.glb`), the runtime format loaded by three.js.

```
gen_player.py    legacy Blender generator for the retired player.glb
                 (active model is now the trimmed Gaelic_Football_3d squad:
                 public/assets/gaelic_player.glb)
gen_ball.py      Sherrin-style oval ball with laces           → public/assets/ball.glb
gen_stadium.py   Melbourne arena (bowl, roof, towers, screens)→ public/assets/stadium.glb
ard_lib.py       shared helpers: armature building, deterministic FK posing,
                 proximity skinning, glTF export
build_assets.py  runs all generators (each in its own bpy process)
headless_stubs.sh  stub X/GL libraries so Blender runs on servers without an X stack
```

## Running it

```bash
node ../../scripts/build-assets.mjs         # from the repo root: npm run assets
# or directly:
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python build_assets.py            # or gen_player.py / gen_ball.py / gen_stadium.py
```

The generated `.glb` files are **committed** so the game runs without Blender;
regenerate them only when you change the models.

## The player rig

- Skeleton: hips → spine → chest → neck → head, shoulder/arm/forearm/hand
  chains, thigh/shin/foot chains (19 joints).
- Mesh: body parts built from primitives (jersey, shorts, socks, boots, skin,
  hair as separate materials, so the game can tint kits per team).
- Skinning: deterministic proximity weighting to the 3 nearest bones
  (headless-safe replacement for automatic weights).
- Animation: poses are armature-space Euler rotations pivoting on each bone
  head, converted to exact pose-bone matrices (Blender's
  `world = parent_world · inv(rest_parent) · rest_self · basis` identity), so
  keyframes are fully deterministic and reproducible.
- Clips: `idle, walk, run, sprint, run_ball, kick, handball, tackle,
  mark_jump, celebrate, hit_deck`.

## Headless servers

Blender links against X11/GL even in background mode. On machines without
those libraries, `headless_stubs.sh` generates tiny stub `.so` files with the
right SONAMEs and symbol versions (and no-ops for everything else) — a
headless Blender never calls into X/GL. `scripts/build-assets.mjs` detects
the situation and sets this up automatically.
