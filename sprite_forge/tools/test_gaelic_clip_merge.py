#!/usr/bin/env python3
"""The Gaelic player keeps its skeleton, clips and parts when one clip is merged into a copy."""
import hashlib, json, os, shutil, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(HERE)
GAME = os.path.join(ROOT, "Gaelic_Football_3d")
TEMPLATE = os.path.join(GAME, "assets", "source", "makehuman_template.glb")
PLAYER = os.path.join(GAME, "assets", "models", "gaelic_player.glb")
PARTS = os.path.join(GAME, "assets", "models", "gaelic_player.parts")
TEX = os.path.join(GAME, "assets", "textures")
sys.path.insert(0, HERE)
from sforge.gaelic_clip import CLIP_NAMES, read_glb, _anim_names

FORGE = os.path.join(HERE, "forge.py")


def run(*args):
    p = subprocess.run([sys.executable, FORGE, "gaelic-clip", *args], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def main():
    assert os.path.isfile(TEMPLATE), TEMPLATE
    assert os.path.isfile(PLAYER) and os.path.isfile(PARTS)
    before = sha(PLAYER)
    code, out = run("check", PLAYER, "--parts", PARTS, "--textures", TEX)
    info = json.loads(out)
    assert code == 0 and info["ok"], out
    assert info["joints"] == 52, info["joints"]
    assert info["meshes"] == 95, info["meshes"]
    for name in CLIP_NAMES:
        assert name in info["clips"], name
    assert sha(PLAYER) == before

    tmp = tempfile.mkdtemp(prefix="gf_clip_")
    try:
        code, out = run("merge", TEMPLATE, TEMPLATE, "--source", "jog", "--name", "bounce",
                        "--out", tmp)
        assert code == 0, out
        doc, _buf = read_glb(os.path.join(tmp, "gaelic_player.glb"))
        names = _anim_names(doc)
        assert "jog" in names and "bounce" in names
        assert len(doc["skins"][0]["joints"]) <= 64
        joints = [doc["nodes"][i]["name"] for i in doc["skins"][0]["joints"]]
        for b in ("pelvis", "foot_l", "foot_r", "hand_l", "hand_r", "head"):
            assert b in joints
        assert os.path.isfile(TEMPLATE)
        nest = os.path.join(tmp, "same")
        os.makedirs(nest)
        shutil.copyfile(TEMPLATE, os.path.join(nest, "gaelic_player.glb"))
        code, out = run("merge", os.path.join(nest, "gaelic_player.glb"), TEMPLATE,
                        "--source", "jog", "--name", "bounce", "--out", nest)
        assert code == 2, out
        man = json.load(open(os.path.join(tmp, "manifest.json"), encoding="utf-8"))
        assert man["licence"].startswith("not asserted")
        assert "CC0" not in man["licence"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("gaelic clip merge: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
