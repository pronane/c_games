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
from sforge.gaelic_clip import CLIP_NAMES, read_glb, _anim_names, write_synthetic_clip

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
        synth = os.path.join(tmp, "synth.glb")
        write_synthetic_clip(TEMPLATE, synth)
        out_dir = os.path.join(tmp, "candidate")
        code, out = run("merge", PLAYER, synth, "--source", "synth_step", "--name", "synth_step",
                        "--parts", PARTS, "--out", out_dir,
                        "--retarget-cmd", "synthetic fixture authored by the test, not a vendor clip")
        assert code == 0, out
        doc, _buf = read_glb(os.path.join(out_dir, "gaelic_player.glb"))
        names = _anim_names(doc)
        for clip in CLIP_NAMES:
            assert clip in names
        assert "synth_step" in names
        assert len(doc["meshes"]) == 95
        assert len(doc["skins"][0]["joints"]) == 52
        man = json.load(open(os.path.join(out_dir, "manifest.json"), encoding="utf-8"))
        assert man["player"]["sha256"] == before
        assert man["player"]["path"] and not os.path.isabs(man["player"]["path"])
        assert "/tmp/" not in json.dumps(man["player"])
        assert man["retarget_command"].startswith("synthetic")
        assert "Not established" in man["rights"]
        assert man["keys"]["pelvis"]["xz_span_m"][1] < 0.1
        assert sha(PLAYER) == before
        # a second write into the same directory is refused
        code, out = run("merge", PLAYER, synth, "--source", "synth_step", "--name", "synth_step",
                        "--out", out_dir)
        assert code == 2, out
        # displacing the shipped run clip needs an explicit flag
        code, out = run("merge", PLAYER, synth, "--source", "synth_step", "--name", "run",
                        "--out", os.path.join(tmp, "nope"))
        assert code == 2 and "replace-clip" in out, out
        # the canonical model path cannot be the output
        code, out = run("merge", PLAYER, synth, "--source", "synth_step", "--name", "synth_step",
                        "--out", os.path.join(GAME, "assets", "models"))
        assert code == 2, out
        assert sha(PLAYER) == before
        for fault in ("time", "quat", "pelvis"):
            bad = os.path.join(tmp, fault + ".glb")
            write_synthetic_clip(TEMPLATE, bad, fault=fault)
            code, out = run("merge", PLAYER, bad, "--source", "synth_step", "--name", "synth_step",
                            "--out", os.path.join(tmp, "bad-" + fault))
            assert code == 1, (fault, out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("gaelic clip merge: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
