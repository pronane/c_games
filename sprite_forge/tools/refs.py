#!/usr/bin/env python3
"""Reference library (v9.4): photos and videos the engine is measured against, learns motions from, and (with consent)
can be trained on later.

    python tools/refs.py add FILE --kind photo|video --person NAME --consent yes|no --licence "..." [--tags a,b] [--note ..]
    python tools/refs.py list
    python tools/refs.py cut ID                     # photo -> cutout.png + landmarks.json (forge.py cutout; pose model)
    python tools/refs.py bench OUT [--engines skin35,photo3d35] [--moves idle,punch,kick]
    python tools/refs.py motions [--move NAME]      # videos -> mocap clips -> library motions (forge.py mocap)
    python tools/refs.py dataset OUT                # consented items only -> manifest for training / fine-tuning

Store: SFS_REFS (default library/refs/, git-ignored).  Files are COPIED into the store with a sha256, so a reference never
changes under a benchmark.  Each record keeps who is in it, whether they agreed (consent), the licence and the source -
the bench and dataset commands skip anything without consent: yes.

What "training from the library" means here:
  1. benchmark   every engine change is scored on every consented photo with tools/quality_report.py (face found,
                 identity, sharpness, BRISQUE, head ratio, colour dE) - BENCH.md shows better / worse per person.
                 This is how parameters (depth ratios, proportion strength, smear, look-at) get tuned - by measurement.
  2. motions     each video becomes a library motion (mocap) usable by every engine at any angle: a growing move set
                 recorded from real people instead of hand keys.
  3. dataset     a manifest (images, cut-outs, landmarks, licence) in a layout used by fine-tuning tools, for the
                 GPU tier later (e.g. a style LoRA for a game's look, or adapting a learned-body model)."""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORGE = os.path.join(HERE, "forge.py")
STORE = os.environ.get("SFS_REFS", os.path.join(HERE, "library", "refs"))
INDEX = os.path.join(STORE, "refs.json")


def load():
    if os.path.isfile(INDEX):
        return json.load(open(INDEX))
    return {"format": "sforge-refs", "version": 1, "items": []}


def save(d):
    os.makedirs(STORE, exist_ok=True)
    json.dump(d, open(INDEX, "w"), indent=1)
    gi = os.path.join(STORE, ".gitignore")
    if not os.path.isfile(gi):
        open(gi, "w").write("*\n!.gitignore\n")          # people's photos never go into the repo by accident


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def cmd_add(a):
    d = load()
    h = sha(a.file)
    if any(i["sha256"] == h for i in d["items"]):
        print("already in the library"); return 0
    iid = "%s_%s" % (a.kind, h[:10])
    dst_dir = os.path.join(STORE, iid); os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, "source" + os.path.splitext(a.file)[1].lower())
    shutil.copy2(a.file, dst)
    for extra in ("cutout.png", "landmarks.json"):          # an existing cut-out next to the photo comes along
        src = os.path.join(os.path.dirname(os.path.abspath(a.file)), extra)
        if a.kind == "photo" and os.path.isfile(src):
            shutil.copy2(src, os.path.join(dst_dir, extra))
    rec = dict(id=iid, kind=a.kind, file=os.path.relpath(dst, STORE), sha256=h, person=a.person, consent=a.consent,
               licence=a.licence, source=a.source or "", tags=[t for t in (a.tags or "").split(",") if t], note=a.note or "",
               added=time.strftime("%Y-%m-%d"))
    d["items"].append(rec); save(d)
    print("added %s (%s, consent %s)" % (iid, a.person, a.consent))
    return 0


def cmd_list(a):
    d = load()
    print("%-20s %-6s %-16s %-8s %-18s %s" % ("id", "kind", "person", "consent", "licence", "tags"))
    for i in d["items"]:
        cut = os.path.isfile(os.path.join(STORE, i["id"], "landmarks.json"))
        print("%-20s %-6s %-16s %-8s %-18s %s%s" % (i["id"], i["kind"], i["person"][:16], i["consent"], i["licence"][:18],
                                                  ",".join(i["tags"]), "  [cut]" if cut else ""))
    return 0


def _item(d, iid):
    for i in d["items"]:
        if i["id"] == iid:
            return i
    raise SystemExit("no reference %s" % iid)


def cmd_cut(a):
    d = load(); i = _item(d, a.id)
    out = os.path.join(STORE, i["id"])
    r = subprocess.run([sys.executable, FORGE, "cutout", os.path.join(STORE, i["file"]), "--person", "largest", "--out", out])
    return r.returncode


def _consented(d, kind):
    return [i for i in d["items"] if i["kind"] == kind and i["consent"] == "yes"]


ENGINES = {"skin0": ["--puppet-engine", "skin", "--motion-style", "polish"],
           "skin35": ["--puppet-engine", "skin", "--motion-style", "polish", "--turn-yaw", "35"],
           "photo3d35": ["--puppet-engine", "photo3d", "--turn-yaw", "35"],
           "photo3d90": ["--puppet-engine", "photo3d", "--turn-yaw", "90"]}


def cmd_bench(a):
    d = load()
    items = [i for i in _consented(d, "photo") if os.path.isfile(os.path.join(STORE, i["id"], "landmarks.json"))]
    if not items:
        raise SystemExit("no consented photos with a cut-out (refs.py add ... --consent yes, then refs.py cut ID)")
    os.makedirs(a.out, exist_ok=True)
    rows = []
    for i in items:
        src = os.path.join(STORE, i["id"])
        builds = []
        for e in a.engines.split(","):
            o = os.path.join(a.out, i["id"], e)
            subprocess.run([sys.executable, FORGE, "build", "--photo", os.path.join(src, "cutout.png"), "--landmarks",
                            os.path.join(src, "landmarks.json"), "--fill", "puppet", "--preset", "fighter14", "--moves", a.moves,
                            "--name", "ref", "--frame", "512x512", "--no-glb", "--no-fbx", "--no-cache", "--out", o] + ENGINES[e],
                           capture_output=True)
            builds += ["--build", "%s=%s" % (e, os.path.join(o, "ref"))]
        # judge against the reference the build actually used: the proportion-corrected cut-out when it was corrected
        sys.path.insert(0, HERE)
        from PIL import Image
        from sforge import proportions as PRO
        lmd = json.load(open(os.path.join(src, "landmarks.json"))); lml = lmd["landmarks"] if isinstance(lmd, dict) else lmd
        ref_img, _, pinfo = PRO.correct(Image.open(os.path.join(src, "cutout.png")), lml, log=lambda *x: None)
        refp = os.path.join(a.out, i["id"], "reference.png"); ref_img.save(refp)
        builds = [b if not b.startswith(tuple(ENGINES)) else b + "@" + refp for b in builds]
        q = os.path.join(a.out, i["id"], "quality")
        subprocess.run([sys.executable, os.path.join(HERE, "tools", "quality_report.py"), "--photo", os.path.join(src, "cutout.png"),
                        "--landmarks", os.path.join(src, "landmarks.json"), "--out", q] + builds, capture_output=True)
        res = json.load(open(os.path.join(q, "quality.json")))
        for e in a.engines.split(","):
            r = res.get(e, {})
            rows.append((i["id"], i["person"], e, r.get("face_found"), r.get("identity_ssim"), r.get("sharpness"),
                         r.get("brisque"), r.get("head_silhouette")))
    f = lambda v, s: (s % v) if isinstance(v, (int, float)) else "-"
    L = ["# Reference benchmark", "", "| ref | person | engine | face found | identity | sharpness | BRISQUE | head/height |", "|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (r[0], r[1], r[2], f(r[3] and 100 * r[3], "%.0f%%"), f(r[4], "%.2f"),
                                                            f(r[5] and 100 * r[5], "%.0f%%"), f(r[6], "%.1f"), f(r[7], "%.3f")))
    eng = a.engines.split(",")
    L += ["", "Mean per engine:", ""]
    for e in eng:
        rs = [r for r in rows if r[2] == e and r[4] is not None]
        if rs:
            L.append("- %s: identity %.2f, sharpness %.0f%%, BRISQUE %.1f over %d people" % (
                e, sum(r[4] for r in rs) / len(rs), 100 * sum((r[5] or 0) for r in rs) / len(rs),
                sum((r[6] or 0) for r in rs) / len(rs), len(rs)))
    open(os.path.join(a.out, "BENCH.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L))
    return 0


def cmd_motions(a):
    d = load()
    vids = _consented(d, "video")
    if a.move:
        vids = [v for v in vids if a.move in v["tags"] or v["note"] == a.move]
    out = os.path.join(STORE, "_mocap")
    for v in vids:
        move = slug = (v["tags"][0] if v["tags"] else v["id"])
        r = subprocess.run([sys.executable, FORGE, "mocap", "--clip", "%s=%s" % (move, os.path.join(STORE, v["file"])),
                            "--name", "refs", "--out", out, "--no-build"])
        print("%s -> mocap_%s %s" % (v["id"], move, "ok" if r.returncode == 0 else "FAILED (pose model? tools/setup_pose.py)"))
    print("use: forge.py build ... --mocap %s/refs_mocap/<move>.json --moves idle,<move>=mocap_<move>:8:14" % out)
    return 0


def cmd_dataset(a):
    d = load()
    os.makedirs(a.out, exist_ok=True)
    man = []
    for i in d["items"]:
        if i["consent"] != "yes":
            continue
        src = os.path.join(STORE, i["id"])
        ent = {"id": i["id"], "kind": i["kind"], "person": i["person"], "licence": i["licence"], "source": i["source"],
               "file": os.path.join(src, os.path.basename(i["file"])), "tags": i["tags"]}
        for extra in ("cutout.png", "landmarks.json"):
            if os.path.isfile(os.path.join(src, extra)):
                ent[extra.split(".")[0]] = os.path.join(src, extra)
        man.append(ent)
    with open(os.path.join(a.out, "metadata.jsonl"), "w") as f:
        for e in man:
            f.write(json.dumps(e) + "\n")
    print("dataset manifest: %d consented items -> %s/metadata.jsonl (skipped %d without consent)" % (
        len(man), a.out, len(d["items"]) - len(man)))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("add"); p.add_argument("file"); p.add_argument("--kind", choices=["photo", "video"], required=True)
    p.add_argument("--person", required=True); p.add_argument("--consent", choices=["yes", "no", "unknown"], required=True)
    p.add_argument("--licence", required=True); p.add_argument("--source"); p.add_argument("--tags"); p.add_argument("--note")
    sp.add_parser("list")
    p = sp.add_parser("cut"); p.add_argument("id")
    p = sp.add_parser("bench"); p.add_argument("out"); p.add_argument("--engines", default="skin0,skin35,photo3d35")
    p.add_argument("--moves", default="idle,punch,kick")
    p = sp.add_parser("motions"); p.add_argument("--move")
    p = sp.add_parser("dataset"); p.add_argument("out")
    a = ap.parse_args(argv)
    return {"add": cmd_add, "list": cmd_list, "cut": cmd_cut, "bench": cmd_bench, "motions": cmd_motions, "dataset": cmd_dataset}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
