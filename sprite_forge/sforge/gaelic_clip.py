"""Merge one animation into a *copy* of the Gaelic player GLB, by bone name.

The game's player is a 52-joint MakeHuman squad (meshes, .parts, kit atlas) plus 32 clips.
`forge.py retarget` writes one clip onto the MakeHuman template and does not merge it back.
This copies that clip's channels onto the squad skeleton without touching meshes, skin,
materials or the other clips, and without writing over the file it read.

    python3 forge.py gaelic-clip check PLAYER.glb --parts gaelic_player.parts --textures assets/textures
    python3 forge.py gaelic-clip merge PLAYER.glb CLIP.glb --source jog --name bounce --out /tmp/gf_candidate --parts gaelic_player.parts

There is no photo-to-Gaelic command. Do not run gaelic_squad.py --install from here.
"""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, struct, sys

# Exact clip names the game requires (src/main.c CLIP_NAMES). An optional "bounce" may be added.
CLIP_NAMES = [
    "run", "drop_kick", "catch", "idle", "kick_run", "hand_pass", "kick_out", "solo",
    "dive_roll", "keeper_ready", "dive_high", "get_up", "run_ball", "dive_save", "pickup",
    "kick_place", "hook", "head_hit", "hit_react", "knocked_down", "trip", "stumble",
    "pushed", "tackle_reach", "celebrate_jump", "jog", "sidestep", "toe_lift", "solo_left",
    "keeper_high_catch", "keeper_scoop", "keeper_idle",
]
REQUIRED_BONES = ("pelvis", "foot_l", "foot_r", "hand_l", "hand_r", "head")
MAX_BONES = 64


def read_glb(path):
    data = open(path, "rb").read()
    if data[:4] != b"glTF":
        raise ValueError("%s is not a GLB" % path)
    length = struct.unpack("<I", data[12:16])[0]
    doc = json.loads(data[20:20 + length])
    off = 20 + length
    blen = struct.unpack("<I", data[off:off + 4])[0]
    return doc, bytearray(data[off + 8:off + 8 + blen])


def write_glb(path, doc, buf):
    blob = bytearray(buf)
    while len(blob) % 4:
        blob.append(0)
    doc = json.loads(json.dumps(doc))
    doc["buffers"] = [{"byteLength": len(blob)}]
    js = json.dumps(doc, separators=(",", ":")).encode()
    while len(js) % 4:
        js += b" "
    out = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(blob))
    out += struct.pack("<II", len(js), 0x4E4F534A) + js
    out += struct.pack("<II", len(blob), 0x004E4942) + bytes(blob)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(out)
    os.replace(tmp, path)


def _names(doc):
    return [n.get("name", "") for n in doc.get("nodes", [])]


def _anim_names(doc):
    return [a.get("name", "") for a in doc.get("animations", [])]


def _parts_rows(path):
    rows = []
    for ln in open(path, encoding="utf-8"):
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        bits = s.split()
        if len(bits) < 3:
            raise ValueError("bad parts line: %s" % ln.rstrip())
        rows.append((int(bits[0]), int(bits[1]), bits[2]))
    return rows


def validate(doc, parts=None, textures=None):
    """Return a list of error strings. Empty means the player still matches the game."""
    err = []
    names = _names(doc)
    joints = []
    if doc.get("skins"):
        joints = [names[i] if i < len(names) else "?" for i in doc["skins"][0].get("joints", [])]
    if not joints:
        err.append("no skin joints")
    elif len(joints) > MAX_BONES:
        err.append("%d joints (game allows %d)" % (len(joints), MAX_BONES))
    for b in REQUIRED_BONES:
        if b not in joints:
            err.append("missing joint %s" % b)
    have = _anim_names(doc)
    for n in CLIP_NAMES:
        if n not in have:
            err.append("missing clip %s" % n)
    meshes = len(doc.get("meshes", []))
    if parts:
        rows = _parts_rows(parts)
        if len(rows) != meshes:
            err.append("parts has %d rows, GLB has %d meshes" % (len(rows), meshes))
        roles = {"body", "kit", "hair", "brows", "lashes", "eyes"}
        for i, _v, role in rows:
            if role not in roles:
                err.append("unknown part role %s" % role)
            if i < 0 or i >= meshes:
                err.append("part index %d out of range" % i)
    if textures:
        try:
            from PIL import Image
        except ImportError:
            err.append("Pillow is required to check kit textures")
            return err
        for name in ("home", "away", "gk_home", "gk_away", "referee", "umpire"):
            p = os.path.join(textures, "kit_%s.png" % name)
            if not os.path.isfile(p):
                err.append("missing %s" % p)
                continue
            im = Image.open(p).convert("RGB")
            w, h = im.size
            if w < 2 or (w % 2):
                err.append("%s width %d is not a split atlas" % (p, w))
                continue
            # Left half is jersey / socks / boots, right half is shorts. They must not be the same picture.
            left = im.crop((0, 0, w // 2, h)).resize((16, 16)).tobytes()
            right = im.crop((w // 2, 0, w, h)).resize((16, 16)).tobytes()
            if left == right:
                err.append("%s left and right halves are identical" % p)
    return err


def _acc_bytes(doc, buf, index):
    acc = doc["accessors"][index]
    view = doc["bufferViews"][acc["bufferView"]]
    ncomp = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[acc["type"]]
    ctype = {5126: 4, 5123: 2, 5121: 1, 5125: 4, 5122: 2, 5120: 1}[acc["componentType"]]
    stride = view.get("byteStride", 0)
    start = view.get("byteOffset", 0) + acc.get("byteOffset", 0)
    count = acc["count"]
    tight = ctype * ncomp
    if stride and stride != tight:
        out = bytearray()
        for k in range(count):
            out += buf[start + k * stride:start + k * stride + tight]
        return bytes(out)
    return bytes(buf[start:start + tight * count])


def merge_clip(player_doc, player_buf, clip_doc, clip_buf, source_name, dest_name):
    """Append or replace one animation. Meshes, nodes and the other clips stay. Returns a report."""
    if dest_name in CLIP_NAMES and dest_name != source_name:
        # Replacing a required clip is allowed only when the caller names it on purpose.
        pass
    src_anims = {a.get("name"): a for a in clip_doc.get("animations", [])}
    if source_name not in src_anims:
        have = ", ".join(src_anims) or "(none)"
        raise ValueError("clip GLB has no animation %r (has: %s)" % (source_name, have))
    src = src_anims[source_name]
    src_nodes = _names(clip_doc)
    dst_index = {n: i for i, n in enumerate(_names(player_doc))}
    buf = bytearray(player_buf)
    accessors = list(player_doc["accessors"])
    views = list(player_doc["bufferViews"])
    used = skipped = 0
    skipped_names = []
    samplers = []
    channels = []
    for ch in src["channels"]:
        node = src_nodes[ch["target"]["node"]]
        if node not in dst_index:
            skipped += 1
            if node not in skipped_names:
                skipped_names.append(node)
            continue
        sm = src["samplers"][ch["sampler"]]
        new_s = {}
        for key, path in (("input", "SCALAR"), ("output", None)):
            raw = _acc_bytes(clip_doc, clip_buf, sm[key])
            while len(buf) % 4:
                buf.append(0)
            views.append({"buffer": 0, "byteOffset": len(buf), "byteLength": len(raw)})
            buf += raw
            old = clip_doc["accessors"][sm[key]]
            acc = {"bufferView": len(views) - 1, "componentType": old["componentType"],
                   "type": old["type"], "count": old["count"]}
            if "min" in old: acc["min"] = old["min"]
            if "max" in old: acc["max"] = old["max"]
            accessors.append(acc)
            new_s[key] = len(accessors) - 1
        new_s["interpolation"] = sm.get("interpolation", "LINEAR")
        samplers.append(new_s)
        channels.append({"sampler": len(samplers) - 1,
                         "target": {"node": dst_index[node], "path": ch["target"]["path"]}})
        used += 1
    if used == 0:
        raise ValueError("no channels mapped onto the player skeleton (skipped %s)" % ", ".join(skipped_names[:12]))
    anim = {"name": dest_name, "channels": channels, "samplers": samplers}
    anims = [a for a in player_doc.get("animations", []) if a.get("name") != dest_name]
    replaced = len(anims) != len(player_doc.get("animations", []))
    anims.append(anim)
    out = dict(player_doc)
    out["accessors"] = accessors
    out["bufferViews"] = views
    out["animations"] = anims
    report = {"dest": dest_name, "source": source_name, "channels": used, "skipped_nodes": skipped,
              "replaced": replaced, "unmapped": skipped_names[:24]}
    return out, buf, report


def _decode(doc, buf, index):
    import numpy as np
    acc = doc["accessors"][index]
    raw = _acc_bytes(doc, buf, index)
    dt = {5126: np.float32, 5123: np.uint16, 5121: np.uint8, 5125: np.uint32}[acc["componentType"]]
    n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[acc["type"]]
    return np.frombuffer(raw, dtype=dt).reshape(acc["count"], n).astype(np.float64)


def inspect_animation(doc, buf, anim):
    """Reject a clip whose keys could not be a real pose. Returns (errors, report)."""
    import numpy as np
    names = _names(doc)
    errors = []
    pelvis = None
    seen = set()
    quat_ok = 0
    for ch in anim.get("channels", []):
        node = names[ch["target"]["node"]] if ch["target"]["node"] < len(names) else "?"
        path = ch["target"]["path"]
        key = (node, path)
        if key in seen:
            errors.append("duplicate channel %s.%s" % (node, path))
        seen.add(key)
        sm = anim["samplers"][ch["sampler"]]
        times = _decode(doc, buf, sm["input"]).reshape(-1)
        values = _decode(doc, buf, sm["output"])
        if times.shape[0] != values.shape[0]:
            errors.append("%s.%s time/value count differ" % (node, path))
            continue
        if not np.all(np.isfinite(times)) or not np.all(np.isfinite(values)):
            errors.append("%s.%s has a non-finite key" % (node, path))
            continue
        if times.shape[0] >= 2 and np.any(np.diff(times) <= 0):
            errors.append("%s.%s times are not strictly increasing" % (node, path))
        if path == "rotation":
            nrm = np.linalg.norm(values, axis=1)
            if np.any(np.abs(nrm - 1.0) > 0.05):
                errors.append("%s rotation quaternion is not unit length" % node)
            else:
                quat_ok += 1
        if node == "pelvis" and path == "translation":
            pelvis = {
                "samples": int(times.shape[0]),
                "xz_span_m": [round(float(values[:, 0].max() - values[:, 0].min()), 4),
                              round(float(values[:, 2].max() - values[:, 2].min()), 4)],
                "y_span_m": round(float(values[:, 1].max() - values[:, 1].min()), 4),
            }
            if np.any(np.abs(values) > 50.0):
                errors.append("pelvis translation is not a metre-scale pose")
    report = {"unique_channels": len(seen), "unit_quaternions": quat_ok, "pelvis": pelvis}
    return errors, report


def write_synthetic_clip(template_glb, out_path, name="synth_step", fault=None):
    """A clip this repo authored (no vendor motion). fault is 'time', 'quat' or 'pelvis'."""
    import numpy as np
    doc, buf = read_glb(template_glb)
    names = _names(doc)
    want = {"pelvis": "translation", "thigh_l": "rotation", "calf_l": "rotation", "foot_l": "rotation"}
    idx = {n: i for i, n in enumerate(names)}
    for n in want:
        if n not in idx:
            raise ValueError("template has no %s" % n)
    times = np.array([0.0, 0.25, 0.5, 0.75], np.float32)
    if fault == "time":
        times = np.array([0.0, 0.5, 0.25, 1.0], np.float32)
    pel = np.array([[0.0, 0.90, 0.0], [0.0, 0.96, 0.02], [0.0, 0.90, 0.0], [0.0, 0.94, -0.02]], np.float32)
    if fault == "pelvis":
        pel[:, 2] = np.array([0, 40, 80, 120], np.float32)

    def quat(angle):
        if fault == "quat" and angle > 0:
            return np.array([0, 0, 0, 0], np.float32)
        return np.array([0, 0, np.sin(angle * 0.5), np.cos(angle * 0.5)], np.float32)

    thigh = np.stack([quat(a) for a in (0.0, 0.6, 0.0, -0.5)]).astype(np.float32)
    calf = np.stack([quat(a) for a in (0.0, -0.8, -0.2, 0.1)]).astype(np.float32)
    foot = np.stack([quat(a) for a in (0.0, 0.3, 0.0, -0.2)]).astype(np.float32)
    tracks = [("pelvis", "translation", pel), ("thigh_l", "rotation", thigh),
              ("calf_l", "rotation", calf), ("foot_l", "rotation", foot)]
    out_buf = bytearray()
    views, accs, samplers, channels = [], [], [], []

    def add(arr):
        raw = np.ascontiguousarray(arr).tobytes()
        while len(out_buf) % 4:
            out_buf.append(0)
        views.append({"buffer": 0, "byteOffset": len(out_buf), "byteLength": len(raw)})
        out_buf.extend(raw)
        return len(views) - 1

    time_view = add(times)
    accs.append({"bufferView": time_view, "componentType": 5126, "type": "SCALAR", "count": 4,
                 "min": [float(times.min())], "max": [float(times.max())]})
    time_acc = 0
    for node, path, values in tracks:
        view = add(values)
        typ = "VEC3" if path == "translation" else "VEC4"
        accs.append({"bufferView": view, "componentType": 5126, "type": typ, "count": int(values.shape[0])})
        samplers.append({"input": time_acc, "output": len(accs) - 1, "interpolation": "LINEAR"})
        channels.append({"sampler": len(samplers) - 1, "target": {"node": idx[node], "path": path}})
    doc["animations"] = [{"name": name, "samplers": samplers, "channels": channels}]
    doc["accessors"] = accs
    doc["bufferViews"] = views
    # Drop bulky images/meshes? Keep the template nodes and skin so bone names match, drop mesh
    # payloads by pointing buffer only at the keys. Nodes that reference missing meshes would be
    # invalid. Keep the original meshes' buffer by concatenating is hard. Write keys-only GLB:
    # retarget/merge only reads nodes + animation channels, which this file has.
    for nd in doc["nodes"]:
        nd.pop("mesh", None)
        nd.pop("skin", None)
    doc.pop("meshes", None)
    doc.pop("skins", None)
    doc.pop("materials", None)
    doc.pop("textures", None)
    doc.pop("images", None)
    doc.pop("samplers", None)
    write_glb(out_path, doc, out_buf)


def _identity(path):
    ab = os.path.abspath(path)
    try:
        rel = os.path.relpath(ab, os.getcwd()).replace("\\", "/")
    except ValueError:
        rel = None
    if not rel or rel.startswith("..") or os.path.isabs(rel):
        return {"name": os.path.basename(ab), "sha256": _sha(ab), "path": None,
                "note": "outside the working directory; the sha256 is the identity"}
    return {"name": os.path.basename(ab), "sha256": _sha(ab), "path": rel}


def _canonical_player_path(path):
    norm = os.path.normpath(os.path.abspath(path)).replace("\\", "/")
    return norm.endswith("/assets/models/gaelic_player.glb") or norm.endswith("/assets/models")


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def cmd_check(a):
    doc, _buf = read_glb(a.player)
    err = validate(doc, a.parts, a.textures)
    info = {
        "joints": len(doc["skins"][0]["joints"]) if doc.get("skins") else 0,
        "meshes": len(doc.get("meshes", [])),
        "clips": _anim_names(doc),
        "ok": not err,
        "errors": err,
    }
    print(json.dumps(info, indent=1))
    return 0 if not err else 1


def cmd_merge(a):
    from sforge import __version__
    player = os.path.abspath(a.player)
    clip = os.path.abspath(a.clip)
    out_dir = os.path.abspath(a.out)
    out_glb = os.path.join(out_dir, "gaelic_player.glb")
    if os.path.abspath(out_glb) in (player, clip) or _canonical_player_path(out_glb) or _canonical_player_path(out_dir):
        print("refusing to write the shipped gaelic_player.glb or over an input", file=sys.stderr)
        return 2
    if os.path.exists(out_glb) and not a.replace:
        print("output already exists; pass --replace to overwrite this candidate", file=sys.stderr)
        return 2
    before = _sha(player)
    doc, buf = read_glb(player)
    cdoc, cbuf = read_glb(clip)
    if a.name in _anim_names(doc) and not a.replace_clip:
        print("clip %r is already on the player; pass --replace-clip to displace it" % a.name, file=sys.stderr)
        return 2
    src_anims = {an.get("name"): an for an in cdoc.get("animations", [])}
    if a.source not in src_anims:
        print("clip GLB has no animation %r" % a.source, file=sys.stderr)
        return 2
    key_err, key_rep = inspect_animation(cdoc, cbuf, src_anims[a.source])
    if key_err:
        print(json.dumps({"ok": False, "errors": key_err, "keys": key_rep}, indent=1))
        return 1
    merged, mbuf, report = merge_clip(doc, buf, cdoc, cbuf, a.source, a.name)
    err = validate(merged, a.parts, a.textures)
    if a.name not in _anim_names(merged):
        err.append("merge did not produce %s" % a.name)
    old = set(_anim_names(doc))
    new = set(_anim_names(merged))
    missing = sorted(old - new - ({a.name} if a.replace_clip else set()))
    if missing:
        err.append("merge dropped clips: %s" % ", ".join(missing))
    if err:
        print(json.dumps({"ok": False, "errors": err, "report": report}, indent=1))
        return 1
    os.makedirs(out_dir, exist_ok=True)
    write_glb(out_glb, merged, mbuf)
    if a.parts:
        shutil.copyfile(a.parts, os.path.join(out_dir, "gaelic_player.parts"))
    if _sha(player) != before:
        print("input player GLB changed under us; refusing", file=sys.stderr)
        return 2
    manifest = {
        "role": "local candidate only",
        "note": "Do not commit this file. The game loads assets/models/gaelic_player.glb unless --model is set.",
        "sprite_forge": __version__,
        "player": _identity(player),
        "clip": _identity(clip),
        "source_animation": a.source,
        "dest_animation": a.name,
        "replaced_existing_clip": report["replaced"],
        "displaced_clip": a.name if report["replaced"] else None,
        "channels_copied": report["channels"],
        "unmapped_nodes": report["unmapped"],
        "keys": key_rep,
        "retarget_command": a.retarget_cmd,
        "merge_command": "python3 forge.py gaelic-clip merge <player> <clip> --source %s --name %s --out <dir>" % (a.source, a.name),
        "parts_copied": bool(a.parts),
        "rights": "Not established. Vendor metadata inside a file is not permission to redistribute, and it is not proof of a violation. Keep the candidate local until the real licence and author are known.",
    }
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)
        f.write("\n")
    print(json.dumps({"ok": True, "out": _identity(out_glb), "report": report, "keys": key_rep}, indent=1))
    return 0


def main(argv):
    p = argparse.ArgumentParser(prog="forge.py gaelic-clip", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="validate joints, required clips, .parts and the kit split")
    c.add_argument("player")
    c.add_argument("--parts")
    c.add_argument("--textures", help="directory of kit_*.png (left jersey/socks/boots, right shorts)")
    m = sub.add_parser("merge", help="copy one clip onto a new player GLB; does not modify the inputs")
    m.add_argument("player")
    m.add_argument("clip", help="GLB from forge.py retarget ... --out (one or more clips)")
    m.add_argument("--source", required=True, help="animation name inside the clip GLB")
    m.add_argument("--name", required=True, help="animation name to write on the player copy")
    m.add_argument("--out", required=True, help="directory for gaelic_player.glb, parts and manifest.json")
    m.add_argument("--parts")
    m.add_argument("--textures")
    m.add_argument("--replace", action="store_true", help="overwrite an existing candidate in --out")
    m.add_argument("--replace-clip", action="store_true", help="displace a clip the player already has")
    m.add_argument("--retarget-cmd", default=None, help="exact forge.py retarget command that produced the clip, stored in the manifest")
    a = p.parse_args(argv)
    if a.cmd == "check":
        return cmd_check(a)
    return cmd_merge(a)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
