"""Build the same body in MakeHuman's own code (MPFB2 in Blender) as a `forge.py capture` fit, to compare (optional).

    blender -b -P tools/capture_vs_makehuman_blender.py -- BODY.json OUT.npy
BODY.json: {"phenotype": {gender, age, muscle, weight, height, proportions, african, asian, caucasian},
            "targets": {"torso/torso-scale-depth-decr": 0.4, ...}}
Writes the MakeHuman base-mesh vertices (all 19,158, MakeHuman space: decimetres, Y up) that MPFB2 produced.
tools/capture_bench.py --vs-makehuman compares them with Sprite Forge's own build of the same body."""
import json
import os
import sys

import numpy as np
import bpy
import addon_utils

argv = sys.argv[sys.argv.index("--") + 1:]
body = json.load(open(argv[0]))
EXT = "bl_ext.user_default.mpfb"
bpy.ops.wm.read_userpref()
if EXT not in bpy.context.preferences.addons:
    addon_utils.enable(EXT, default_set=True)
from bl_ext.user_default.mpfb.services.humanservice import HumanService as HS  # noqa: E402

ph = {"gender": 0.5, "age": 0.5, "muscle": 0.5, "weight": 0.5, "height": 0.5, "proportions": 0.5,
      "cupsize": 0.5, "firmness": 0.5, "race": {"african": 1 / 3.0, "asian": 1 / 3.0, "caucasian": 1 / 3.0}}
for k, v in body.get("phenotype", {}).items():
    if k in ("african", "asian", "caucasian"):
        ph["race"][k] = v
    else:
        ph[k] = v
info = {"phenotype": ph, "rig": "", "eyes": "", "eyebrows": "", "eyelashes": "", "hair": "", "proxy": "", "tongue": "",
        "teeth": "", "clothes": [], "expressions": [], "skin_mhmat": "", "skin_material_type": "NONE",
        "targets": [{"target": k.split("/")[-1], "value": float(v)} for k, v in body.get("targets", {}).items()]}
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
st = HS.get_default_deserialization_settings(); st["subdiv_levels"] = 0
bm = HS.deserialize_from_dict(info, st)
me = bm.data
n = len(me.vertices)
keys = me.shape_keys.key_blocks if me.shape_keys else []
basis = np.zeros(n * 3); (keys[0].data if keys else me.vertices).foreach_get("co", basis); basis = basis.reshape(n, 3)
out = basis.copy()
for k in list(keys)[1:]:
    if k.value and not k.mute:
        c = np.zeros(n * 3); k.data.foreach_get("co", c); out += k.value * (c.reshape(n, 3) - basis)
mh = np.stack([out[:, 0], out[:, 2], -out[:, 1]], 1) / 0.1
np.save(argv[1], mh)
print("MPFB vertices", mh.shape)
sys.stdout.flush()
os._exit(0)
