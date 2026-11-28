#!/usr/bin/env python3
"""v11.41: the "models" and "environments" library kinds."""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
sys.path.insert(0, ROOT)
from sforge import library as L  # noqa: E402
from sforge import modellib as MDL  # noqa: E402
from sforge import environments as E  # noqa: E402

fails = []


def check(ok, msg):
    print(("ok   " if ok else "FAIL ") + msg)
    if not ok:
        fails.append(msg)


tmp = tempfile.mkdtemp()
try:
    lib = L.Library(os.path.join(tmp, "lib"))
    check("models" in L.KINDS and "environments" in L.KINDS, "new kinds registered")

    # ---- models
    done = dict(MDL.import_registry(lib))
    check(len(done) == len(json.load(open(MDL.REGISTRY))["models"]), "every registry model imported (%d)" % len(done))
    check(all(not p for p in done.values()), "imported models validate %s" % {k: v for k, v in done.items() if v})
    lib.scan(import_inbox=False)
    m = MDL.load(lib, "lifter_v1")
    check(m["task"] == "lifter" and m["version"] == 1 and m["trained_here"] and m["stored"], "lifter: task, version, trained here, stored")
    check(m["sha256"] and os.path.isfile(MDL.weights_path(lib, "lifter_v1")), "lifter weights copied with a checksum")
    check(os.path.isfile(os.path.join(lib.path("models", "lifter_v1"), "lifter_v1.json")), "lifter's joint/normalisation json kept")
    check(MDL.load(lib, "yolox_m_humanart")["task"] == "detector" and MDL.load(lib, "rtmpose_l_halpe26")["task"] == "pose2d",
          "tasks read from the registry")
    check(lib.licence("yolox_m_humanart")["ml_training"] == "unknown", "a registry caveat (Human-Art) leaves ml_training unknown")
    check(lib.licence("lifter_v1")["spdx"] == "MIT" and lib.licence("lifter_v1")["ml_training"] == "yes", "lifter licence MIT, trainable")
    check(MDL.latest(lib, "lifter")[0] == "lifter_v1", "latest lifter")
    meta = dict(MDL.load(lib, "lifter_v1"), version=2, metrics={"val_mpjpe_cm": 9.1})
    lib.add_model("lifter_v2", meta, lib.licence("lifter_v1"), [MDL.weights_path(lib, "lifter_v1")])
    check(MDL.latest(lib, "lifter")[0] == "lifter_v2", "a newer version wins")
    # a model trained on data that may not train is flagged and refused by pack
    bad = MDL.blank_model("lmm_v1", "motion_matching", 1)
    bad.update(trained_here=True, url="https://example.invalid/lmm.onnx",
               trained_on=[dict(dataset="soccertrack", ml_training="yes"), dict(dataset="rohr", ml_training="unknown")])
    lic = L.blank_licence("yes", "yes"); lic.update(spdx="MIT", author="me")
    _, probs = lib.add_model("lmm_v1", bad, lic)
    check(any("rohr" in p for p in probs), "training on ml_training=unknown data is a problem")
    e = lib.entry("models", "lmm_v1")
    check(e["problems"] and e["task"] == "motion_matching", "library entry carries the problems")
    try:
        lib.pack(os.path.join(tmp, "bad.sfpack"), ["lmm_v1"], log=lambda s: None)
        check(False, "pack refuses that model")
    except PermissionError as x:
        check("rohr" in str(x), "pack refuses that model")
    check(MDL.validate_model(dict(task="nope", version="x")) and True, "bad task / version rejected")

    # ---- environments
    for n, r in E.PRESETS.items():
        check(not E.validate(r), "preset %s validates" % n)
    added = E.seed_presets(lib)
    check(sorted(added) == sorted(E.PRESETS), "seed puts every preset in the library")
    lib.scan(import_inbox=False)
    check(E.validate(dict(sport="soccer", stadium=dict(preset="nope"))), "unknown stadium preset rejected")
    check(any("turf" in p for p in E.validate(dict(sport="aussie_rules", stadium=None, pitch={}))), "no turf for Aussie rules")
    check(any("touchline" in p for p in E.validate(dict(sport="soccer", stadium=None, touchline={}))), "touchline needs a stadium")
    out = os.path.join(tmp, "built")
    files = E.build(E.load(lib, "soccer_ground"), out)
    want = {"stadium", "seats", "pitch", "crowd", "adboards", "goals", "touchline", "touchline_props", "environment.json"}
    check(want <= set(files) and all(os.path.isfile(p) for p in files.values()), "build writes every part")
    man = json.load(open(files["environment.json"]))
    check(man["built"]["stadium"] == "stadium.glb" and man["info"]["seats"] > 1000 and man["info"]["touchline_people"] > 10,
          "environment.json lists files, seats and touchline people")
    f2 = E.build(E.PRESETS["aussie_oval"], os.path.join(tmp, "oval"))
    check("pitch" not in f2 and "goals" not in f2 and "stadium" in f2, "parts a sport lacks are skipped")
    e = lib.entry("environments", "soccer_bowl")
    check(e["sport"] == "soccer" and "stadium" in e["parts"] and not e["problems"], "environment entry")
    check(lib.licence("environments/soccer_bowl")["spdx"] == "CC0-1.0", "presets are CC0")

    # ---- packs round-trip both kinds
    pk = os.path.join(tmp, "p.sfpack")
    lib.pack(pk, ["lifter_v1", "soccer_bowl", "gaelic_ground"], log=lambda s: None)
    rep = L.verify(pk)
    check(rep["ok"], "pack of a model + environments verifies %s" % rep["problems"])
    lib2 = L.Library(os.path.join(tmp, "lib2"))
    lib2.install(pk, accept=True, log=lambda s: None)
    check(lib2.names("models") == ["lifter_v1"] and sorted(lib2.names("environments")) == ["gaelic_ground", "soccer_bowl"],
          "install puts them back")
    check(MDL.load(lib2, "lifter_v1")["sha256"] == L.sha256_file(MDL.weights_path(lib2, "lifter_v1")), "weights intact")
    try:
        lib.load_rig("soccer_bowl")
        check(False, "load_rig refuses an environment")
    except KeyError:
        check(True, "load_rig refuses an environment")

    # ---- CLI
    env = dict(os.environ, SFS_LIBRARY=os.path.join(tmp, "lib3"))
    forge = os.path.join(ROOT, "forge.py")

    def run(*a):
        o = subprocess.run([sys.executable, forge, "library"] + list(a), capture_output=True, text=True, env=env)
        return o.returncode, o.stdout + o.stderr
    rc, o = run("models", "import-registry")
    check(rc == 0 and "lifter_v1" in o, "cli: models import-registry")
    rc, o = run("envs", "seed")
    rc, o = run("envs", "add", "--name", "night_derby", "--from", "soccer_classic", "--set", "crowd.fill=1.0", "--set", "pitch.mow=rings")
    check(rc == 0 and "night_derby" in o, "cli: envs add with --set")
    r = json.load(open(os.path.join(tmp, "lib3", "environments", "night_derby", "environment.json")))
    check(r["crowd"]["fill"] == 1.0 and r["pitch"]["mow"] == "rings" and r["stadium"]["preset"] == "classic", "--set applied")
    rc, o = run("list")
    check(rc == 0 and "model " in o and "env " in o and "night_derby" in o, "cli: list shows both kinds")
    rc, o = run("models", "add", "--name", "lmm_v1", "--task", "motion_matching", "--url", "https://example.invalid/x.onnx",
                "--trained-on", "rohr=unknown", "--spdx", "MIT", "--author", "me")
    check(rc != 0 and "rohr" in o, "cli: models add flags untrainable data")
finally:
    shutil.rmtree(tmp)

print("\n%d failed" % len(fails) if fails else "\nall models/environments checks passed")
sys.exit(1 if fails else 0)
