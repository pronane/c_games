#!/usr/bin/env python3
"""An external mesh fitted onto the Gaelic template keeps the 52 joints and the 32 clips."""
import hashlib, json, os, subprocess, sys, tempfile
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(HERE)
GAME = os.path.join(ROOT, "Gaelic_Football_3d")
TEMPLATE = os.path.join(GAME, "assets", "source", "makehuman_template.glb")
PLAYER = os.path.join(GAME, "assets", "models", "gaelic_player.glb")
PARTS = os.path.join(GAME, "assets", "models", "gaelic_player.parts")
FIXTURE = os.path.join(HERE, "testdata", "gaelic_fit_humanoid.obj")
sys.path.insert(0, HERE)
from sforge.gaelic_clip import CLIP_NAMES, read_glb, _anim_names
from sforge.gaelic_fit import (load_body, fit_arrays, arms_to_tpose, procedural_humanoid, write_obj,
                               animation_signature)

FORGE = os.path.join(HERE, "forge.py")


def run(*args):
    p = subprocess.run([sys.executable, FORGE, "gaelic-fit", *args], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def _agree(body, fitted):
    if len(fitted["V"]) != len(body["V"]):
        return None, None
    dom_n = fitted["J"][np.arange(len(fitted["J"])), np.argmax(fitted["W"], 1)]
    dom_o = body["J"][np.arange(len(body["J"])), np.argmax(body["W"], 1)]
    names = body["names"]
    arm = np.array([names[int(d)].split("_")[0] in ("upperarm", "lowerarm", "hand", "clavicle")
                    or names[int(d)].startswith(("index", "middle", "ring", "pinky", "thumb"))
                    for d in dom_o])
    return float((dom_n == dom_o).mean()), float((dom_n[arm] == dom_o[arm]).mean())


def main():
    assert os.path.isfile(TEMPLATE) and os.path.isfile(PLAYER) and os.path.isfile(FIXTURE)
    before_p, before_t = sha(PLAYER), sha(TEMPLATE)
    before_parts = sha(PARTS)
    code, out = run(FIXTURE, "--out", os.path.join(GAME, "assets", "models"))
    assert code == 2 and "assets/models" in out, out
    assert sha(PLAYER) == before_p and sha(TEMPLATE) == before_t

    tmp = tempfile.mkdtemp(prefix="gf_fit_")
    try:
        out_dir = os.path.join(tmp, "box")
        code, out = run(FIXTURE, "--template", TEMPLATE, "--out", out_dir)
        assert code == 0, out
        info = json.loads(out)
        assert info["ok"] and info["pose"] == "T" and info["warp_arms"]
        assert info["joints"] == 52 and info["channels_match_template"]
        assert info["unweighted"] == 0 and info["max_influences"] <= 4
        assert abs(info["weight_sum"][0] - 1) < 0.02 and abs(info["weight_sum"][1] - 1) < 0.02
        assert info["deform_flags"] == []
        doc, _buf = read_glb(os.path.join(out_dir, "fitted.glb"))
        assert len(doc["meshes"]) == 1
        assert len(doc["skins"][0]["joints"]) == 52
        names = _anim_names(doc)
        for clip in CLIP_NAMES:
            assert clip in names, clip
        joints, sig = animation_signature(os.path.join(out_dir, "fitted.glb"))
        t_joints, t_sig = animation_signature(TEMPLATE)
        p_joints, p_sig = animation_signature(PLAYER)
        assert list(joints) == list(t_joints) == list(p_joints)
        assert sig == t_sig == p_sig
        assert all(b in joints for b in ("pelvis", "foot_l", "foot_r", "hand_l", "hand_r", "head"))
        man = json.load(open(os.path.join(out_dir, "manifest.json"), encoding="utf-8"))
        assert man["source_mesh"]["sha256"] == sha(FIXTURE)
        assert man["template"]["path"] == "Gaelic_Football_3d/assets/source/makehuman_template.glb"
        assert man["template"]["sha256"] == before_t
        assert man["squad"]["channels_match"] and man["squad"]["joints_match"]
        assert man["command"].startswith("python3 forge.py gaelic-fit")
        assert "makehuman_template.glb" in man["command"]
        assert "Not compatible" in man["kit_atlas"]
        assert any("Fingers" in g for g in man["gaps"])
        parts = open(os.path.join(out_dir, "fitted.parts"), encoding="utf-8").read().strip().splitlines()
        assert parts[-1] == "0 0 body"
        # a second write is refused; the shipped files stay put
        code, out = run(FIXTURE, "--out", out_dir)
        assert code == 2 and "replace" in out, out
        assert sha(PLAYER) == before_p and sha(PARTS) == before_parts

        z_obj = os.path.join(tmp, "z.obj")
        write_obj(z_obj, *procedural_humanoid("T", up="Z"))
        code, out = run(z_obj, "--out", os.path.join(tmp, "z"))
        assert code == 0 and json.loads(out)["pose"] == "T", out

        wide = os.path.join(tmp, "wide.obj")
        write_obj(wide, *procedural_humanoid("T", arm_span=2.3))
        code, out = run(wide, "--out", os.path.join(tmp, "wide"))
        assert code == 0 and json.loads(out)["pose"] == "T", out

        a_obj = os.path.join(tmp, "a.obj")
        write_obj(a_obj, *procedural_humanoid("A"))
        code, out = run(a_obj, "--out", os.path.join(tmp, "a"))
        assert code == 0 and json.loads(out)["pose"] == "A" and json.loads(out)["warp_arms"] is False, out

        bad = os.path.join(tmp, "bad.obj")
        write_obj(bad, *procedural_humanoid("raised"))
        code, out = run(bad, "--out", os.path.join(tmp, "bad"))
        assert code == 1 and "pose" in out.lower(), out
        assert not os.path.isfile(os.path.join(tmp, "bad", "fitted.glb"))
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    body = load_body(TEMPLATE)
    posed = arms_to_tpose(body["V"], body["joints"], body["names"])
    fitted = fit_arrays(posed, body["F"], body, stand=True, smooth=4)
    all_a, arm_a = _agree(body, fitted)
    assert fitted["report"]["pose"] == "T" and fitted["report"]["warp_arms"]
    assert fitted["report"]["surface_dist_mean_m"] < 0.02, fitted["report"]
    assert all_a is not None and all_a >= 0.90, all_a
    assert arm_a >= 0.80, arm_a
    ident = fit_arrays(body["V"], body["F"], body, stand=True, smooth=4)
    assert ident["report"]["pose"] == "A" and ident["report"]["warp_arms"] is False
    all_a, _arm = _agree(body, ident)
    assert all_a >= 0.90, all_a
    assert sha(PLAYER) == before_p and sha(TEMPLATE) == before_t and sha(PARTS) == before_parts
    print("gaelic fit: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
