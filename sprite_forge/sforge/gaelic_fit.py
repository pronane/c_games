"""Fit an external humanoid mesh onto the Gaelic 52-joint skeleton.

The skeleton, inverse binds and all 32 clips come from
``Gaelic_Football_3d/assets/source/makehuman_template.glb`` (the same rest pose and the same
clip bytes as the shipped squad). The new mesh is stood up with the library orient path, moved
onto that rest pose, and skinned by barycentric transfer from the template body. Output is a
scratch GLB. This does not write ``assets/models`` or ``assets/textures``.

    python3 forge.py gaelic-fit MESH.glb --out /tmp/gf_fit
    python3 forge.py gaelic-fit MESH.obj --out /tmp/gf_fit --preview

A Meshy / Rodin mesh is an input you export yourself. This command does not call those services
and does not generate a person.
"""
from __future__ import annotations
import hashlib, io, json, os, shlex, sys
import numpy as np

from . import __version__, gaelic_clip, glbpack
from .glbpack import _acc_bytes

CLIP_CHECK = ("idle", "run", "kick_run", "catch", "solo")
GAPS = [
    "Fingers are still the template hand. fitted.grip pushes the bone targets out by the fingertip pad so the skin clears a 0.11 m ball by about 1.2 cm. The game reads that file only when it sits beside the model.",
    "Loose clothing, hair, a skirt, a cape, or a prop is weighted to the nearest body surface and can candy-wrap.",
    "The face is not retargeted. It rides with the head bone.",
    "Kit shells use the squad atlas (left half jersey/socks/boots, right half shorts). Hands, the head and the lower arms stay on the body mesh and are not recolored per team.",
    "The chest apex is flattened on both sides. The rest mesh was already symmetric; the right side was the one that read as a breast.",
    "The source is scaled to the template height (about 1.74 m). Limb lengths are only approximately matched.",
    "Poses other than a standing T-pose, A-pose, or arms-down stance are rejected (arms raised, arms reaching forward, a knee bend, a sit).",
]


class FitRejected(Exception):
    def __init__(self, message, info=None):
        super().__init__(message)
        self.info = info or {}


def _repo_template():
    root = gaelic_clip._repo_root()
    if not root:
        return None
    return os.path.join(root, "Gaelic_Football_3d", "assets", "source", "makehuman_template.glb")


def _repo_player():
    root = gaelic_clip._repo_root()
    if not root:
        return None
    return os.path.join(root, "Gaelic_Football_3d", "assets", "models", "gaelic_player.glb")


def _forbidden(path):
    norm = os.path.normpath(os.path.abspath(path)).replace("\\", "/")
    if gaelic_clip._canonical_player_path(norm):
        return True
    if "/assets/models/" in norm or norm.endswith("/assets/models"):
        return True
    if "/assets/textures/" in norm or norm.endswith("/assets/textures"):
        return True
    return False


def _rel(path):
    """Repo-relative path when the file or directory lives in the repo. Directories are not hashed."""
    ab = os.path.abspath(path)
    root = gaelic_clip._repo_root()
    if root:
        rel = os.path.relpath(ab, root).replace("\\", "/")
        if rel and not rel.startswith("..") and not os.path.isabs(rel):
            return rel
    return ab


# ---------------------------------------------------------------- template body
def _read(path):
    return glbpack.read_glb(path)


def load_body(path):
    """Skin-joint order, bind positions, and the body mesh that owns the weights."""
    j, buf = _read(path)
    sk = j["skins"][0]
    names = [j["nodes"][i].get("name", "") for i in sk["joints"]]
    ibm = np.frombuffer(_acc_bytes(j, buf, sk["inverseBindMatrices"]), np.float32).reshape(-1, 4, 4).transpose(0, 2, 1)
    P = np.linalg.inv(ibm.astype(np.float64))[:, :3, 3]
    pr = j["meshes"][0]["primitives"][0]
    V = np.frombuffer(_acc_bytes(j, buf, pr["attributes"]["POSITION"]), np.float32).astype(np.float64).reshape(-1, 3)
    idx_dt = np.uint32 if j["accessors"][pr["indices"]]["componentType"] == 5125 else np.uint16
    F = np.frombuffer(_acc_bytes(j, buf, pr["indices"]), idx_dt).astype(np.int32).reshape(-1, 3)
    jc = j["accessors"][pr["attributes"]["JOINTS_0"]]["componentType"]
    J = np.frombuffer(_acc_bytes(j, buf, pr["attributes"]["JOINTS_0"]), {5121: np.uint8, 5123: np.uint16}[jc]).astype(np.int32).reshape(-1, 4)
    W = np.frombuffer(_acc_bytes(j, buf, pr["attributes"]["WEIGHTS_0"]), np.float32).astype(np.float64).reshape(-1, 4)
    UV = np.frombuffer(_acc_bytes(j, buf, pr["attributes"]["TEXCOORD_0"]), np.float32).astype(np.float64).reshape(-1, 2)
    idx = {n: i for i, n in enumerate(names)}
    v = P[idx["hand_l"]] - P[idx["upperarm_l"]]
    drop = float(np.degrees(np.arctan2(-v[1], np.linalg.norm(v[[0, 2]]) + 1e-12)))
    fwd = float(v[2] / (np.linalg.norm(v) + 1e-12))
    return {"path": path, "doc_names": names, "joints": P, "names": names, "index": idx,
            "V": V, "F": F, "J": J, "W": W, "UV": UV, "height": float(V[:, 1].ptp()), "ymin": float(V[:, 1].min()),
            "arm_drop": drop, "arm_fwd": fwd, "dense": _dense(J, W, len(names))}


def animation_signature(path):
    """Clip name -> sorted (joint name, path, sha256 of time+value bytes). Node indices are not compared."""
    j, buf = _read(path)
    names = [n.get("name", "") for n in j.get("nodes", [])]
    out = {}
    for anim in j.get("animations", []):
        rows = []
        for ch in anim["channels"]:
            sm = anim["samplers"][ch["sampler"]]
            raw = _acc_bytes(j, buf, sm["input"]) + _acc_bytes(j, buf, sm["output"])
            node = names[ch["target"]["node"]] if ch["target"]["node"] < len(names) else "?"
            rows.append((node, ch["target"]["path"], hashlib.sha256(raw).hexdigest()))
        out[anim.get("name", "")] = tuple(sorted(rows))
    joints = tuple(names[i] for i in j["skins"][0]["joints"]) if j.get("skins") else ()
    return joints, out


def _dense(J, W, nb):
    D = np.zeros((len(J), nb), np.float64)
    ii = np.arange(len(J))
    for k in range(J.shape[1]):
        np.add.at(D, (ii, np.clip(J[:, k], 0, nb - 1)), W[:, k])
    s = D.sum(1, keepdims=True)
    s[s == 0] = 1
    return D / s


# ---------------------------------------------------------------- orientation
def _rot_between(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    na = np.linalg.norm(a); nb = np.linalg.norm(b)
    if na < 1e-12 or nb < 1e-12:
        return np.eye(3)
    a = a / na; b = b / nb
    c = np.cross(a, b); d = float(np.dot(a, b))
    if np.linalg.norm(c) < 1e-8:
        if d > 0:
            return np.eye(3)
        axis = np.array([1.0, 0, 0]) if abs(a[0]) < 0.9 else np.array([0.0, 1.0, 0])
        axis = axis - a * np.dot(axis, a)
        axis /= np.linalg.norm(axis)
        K = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
        return np.eye(3) + 2 * K @ K
    K = np.array([[0, -c[2], c[1]], [c[2], 0, -c[0]], [-c[1], c[0], 0]])
    return np.eye(3) + K + K @ K * (1.0 / (1.0 + d))


def _apply_R(V, R):
    return np.asarray(V, float) @ np.asarray(R, float).T


def human_score(V):
    """Higher when Y looks like a standing humanoid (narrow head, arms allowed in the upper band)."""
    if len(V) < 8:
        return -1e9
    ymin = float(V[:, 1].min()); H = float(V[:, 1].ptp())
    if H < 1e-8:
        return -1e9
    def span(mask):
        pts = V[mask]
        return float(pts[:, 0].ptp()) if len(pts) >= 5 else 0.0
    top = V[:, 1] > ymin + 0.88 * H
    upper = (V[:, 1] > ymin + 0.62 * H) & (V[:, 1] < ymin + 0.84 * H)
    bot = V[:, 1] < ymin + 0.12 * H
    # A head is a narrow cap. Penalise only a cap as wide as a torso (the body is lying across Y).
    # A wide upper band is a T-pose and should not be mistaken for height.
    return (H + 0.35 * span(upper)
            - 3.0 * max(0.0, span(top) - 0.22 * H)
            - 0.8 * max(0.0, span(bot) - 0.45 * H))


def best_upright(V):
    """Map the axis that scores as 'up' onto +Y. Identity when the mesh is already standing."""
    best_R, best_s = np.eye(3), human_score(V)
    for axis in range(3):
        for sgn in (1.0, -1.0):
            up = np.zeros(3); up[axis] = sgn
            R = _rot_between(up, [0, 1, 0])
            s = human_score(_apply_R(V, R))
            if s > best_s + 1e-6:
                best_s, best_R = s, R
    return best_R, best_s


def _yaw90(V, sign):
    c, s = 0.0, float(sign)
    R = np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], float)
    return _apply_R(V, R)


def arms_along_x(V):
    """Turn about Y so the wide upper-body axis is X (arms), not Z."""
    H = float(V[:, 1].ptp()); ymin = float(V[:, 1].min())
    band = (V[:, 1] > ymin + 0.50 * H) & (V[:, 1] < ymin + 0.90 * H)
    pts = V[band] if band.sum() > 20 else V
    if pts[:, 2].ptp() > pts[:, 0].ptp() * 1.12:
        a = _yaw90(V, 1); b = _yaw90(V, -1)
        ba = a[(a[:, 1] > ymin + 0.5 * H)]
        bb = b[(b[:, 1] > ymin + 0.5 * H)]
        # either facing is corrected later; pick the turn that keeps a wide X span
        V = a if (ba[:, 0].ptp() if len(ba) else 0) >= (bb[:, 0].ptp() if len(bb) else 0) else b
        return V, True
    return V, False


def _toe_z(V):
    """Mean Z of the far end of each foot, relative to the ankle. Positive means the feet point +Z."""
    ymin = float(V[:, 1].min()); H = float(V[:, 1].ptp()); cx = float(np.median(V[:, 0]))
    zs = []
    for sign in (1, -1):
        m = (V[:, 1] < ymin + 0.16 * H) & ((V[:, 0] - cx) * sign > 0.02 * H)
        if m.sum() < 6:
            continue
        pts = V[m]
        top = pts[pts[:, 1] >= np.percentile(pts[:, 1], 90)]
        ankle = np.median(top, 0)
        d = np.linalg.norm(pts[:, [0, 2]] - ankle[[0, 2]], axis=1)
        far = pts[d >= np.percentile(d, 65)]
        zs.append(float((far.mean(0) - ankle)[2]))
    return float(np.mean(zs)) if zs else 0.0


def face_plus_z(V):
    if _toe_z(V) < -0.02 * max(float(V[:, 1].ptp()), 1e-6):
        V = _yaw90(_yaw90(V, 1), 1)  # 180 deg
        return V, True
    return V, False


def _ground_xz(V):
    V = np.array(V, float, copy=True)
    V[:, 1] -= V[:, 1].min()
    cx = float(np.median(V[:, 0])); cz = float(np.median(V[:, 2]))
    V[:, 0] -= cx; V[:, 2] -= cz
    return V


def stand_mesh(V, use_orient_fix=True):
    """Upright, arms along X, feet pointing +Z, feet on y=0. Used after library orient for an unrigged mesh."""
    notes = []
    if use_orient_fix:
        R, _ = best_upright(V)
        if not np.allclose(R, np.eye(3), atol=1e-6):
            V = _apply_R(V, R)
            notes.append("stood the mesh up (+Y); the longest-axis orient had the body on its side")
        V = _ground_xz(V)
        V, turned = arms_along_x(V)
        if turned:
            notes.append("turned about Y so the arms lie along X")
            V = _ground_xz(V)
        V, flipped = face_plus_z(V)
        if flipped:
            notes.append("turned 180 deg so the feet point +Z (the template's forward)")
            V = _ground_xz(V)
    else:
        V = _ground_xz(V)
    return V, notes


# ---------------------------------------------------------------- landmarks and pose
def _seg_dist(V, a, b):
    ab = np.asarray(b, float) - np.asarray(a, float)
    L2 = float(np.dot(ab, ab)) + 1e-12
    t = np.clip((V - a) @ ab / L2, 0.0, 1.0)
    return np.linalg.norm(V - (a + t[:, None] * ab), axis=1), t


def estimate_landmarks(V):
    ymin = float(V[:, 1].min()); H = float(V[:, 1].max() - ymin)
    cx = float(np.median(V[np.abs(V[:, 0]) < 0.25 * H, 0])) if np.any(np.abs(V[:, 0]) < 0.25 * H) else 0.0
    band = (V[:, 1] > ymin + 0.35 * H) & (V[:, 1] < ymin + 0.82 * H) & (np.abs(V[:, 0] - cx) < 0.09 * H)
    cz = float(np.percentile(V[band, 2], 42)) if band.sum() > 30 else float(np.median(V[:, 2]))

    def y_at(f):
        return ymin + f * H

    y_s = y_at(0.80)
    sb = V[np.abs(V[:, 1] - y_s) < 0.035 * H]
    sc = sb[np.abs(sb[:, 0] - cx) < 0.125 * H]
    half = float(np.percentile(np.abs(sc[:, 0] - cx), 90)) if len(sc) > 15 else 0.11 * H
    half = float(np.clip(half, 0.09 * H, 0.16 * H))
    shL = np.array([cx + half, y_s, cz]); shR = np.array([cx - half, y_s, cz])
    upper = V[V[:, 1] > ymin + 0.40 * H]
    if len(upper) < 8:
        upper = V
    tipL = upper[int(np.argmax(upper[:, 0]))].copy()
    tipR = upper[int(np.argmin(upper[:, 0]))].copy()

    def inset(sh, tip):
        d = tip - sh
        n = np.linalg.norm(d) + 1e-12
        return tip - d / n * min(0.08 * H, 0.35 * n)

    def cluster(y, sign):
        m = (np.abs(V[:, 1] - y) < 0.05 * H) & ((V[:, 0] - cx) * sign > 0.02 * H) & ((V[:, 0] - cx) * sign < 0.20 * H)
        if m.sum() < 6:
            return np.array([cx + sign * 0.09 * H, y, cz])
        p = np.median(V[m], 0)
        return p

    def ankle(sign):
        m = (V[:, 1] < ymin + 0.12 * H) & ((V[:, 0] - cx) * sign > 0.015 * H)
        if m.sum() < 6:
            return np.array([cx + sign * 0.10 * H, ymin + 0.05 * H, cz])
        pts = V[m]
        top = pts[pts[:, 1] > np.percentile(pts[:, 1], 60)]
        return np.median(top, 0)

    pel = np.array([cx, y_at(0.535), cz])
    return {"pelvis": pel, "head": np.array([cx, y_at(0.915), cz]),
            "shL": shL, "shR": shR, "wL": inset(shL, tipL), "wR": inset(shR, tipR),
            "tipL": tipL, "tipR": tipR,
            "hipL": cluster(y_at(0.533), 1), "hipR": cluster(y_at(0.533), -1),
            "kL": cluster(y_at(0.29), 1), "kR": cluster(y_at(0.29), -1),
            "aL": ankle(1), "aR": ankle(-1),
            "cx": cx, "cz": cz, "H": H, "ymin": ymin, "half": half}


def _drop(a, b):
    v = np.asarray(b, float) - np.asarray(a, float)
    return float(np.degrees(np.arctan2(-v[1], np.linalg.norm(v[[0, 2]]) + 1e-12)))


def _fwd(a, b):
    v = np.asarray(b, float) - np.asarray(a, float)
    return float(v[2] / (np.linalg.norm(v) + 1e-12))


def classify_pose(lm, tmpl):
    dL, dR = _drop(lm["shL"], lm["wL"]), _drop(lm["shR"], lm["wR"])
    fL, fR = _fwd(lm["shL"], lm["wL"]), _fwd(lm["shR"], lm["wR"])
    span = abs(float(lm["tipL"][0] - lm["tipR"][0]))
    H = float(lm["H"])
    info = {"drop_l": round(dL, 2), "drop_r": round(dR, 2), "fwd_l": round(fL, 3), "fwd_r": round(fR, 3),
            "span_m": round(span, 3), "template_drop": round(tmpl["arm_drop"], 2), "template_fwd": round(tmpl["arm_fwd"], 3)}
    if abs(dL - dR) > 32:
        raise FitRejected("the two arms are not in the same pose (one is raised, bent, or missing). A T-pose or an A-pose is required.", info)
    if min(dL, dR) < -12:
        raise FitRejected("an arm is raised above the shoulder. This fit only handles a T-pose, an A-pose, or arms hanging down.", info)
    if max(dL, dR) > 115:
        raise FitRejected("an arm points down behind the body. This fit only handles a T-pose, an A-pose, or arms hanging down.", info)
    reach = span < 0.28 * H and max(dL, dR) < 75
    if reach:
        raise FitRejected("the hands are in front of the chest, not out to the sides. Export a T-pose or an A-pose.", info)
    if abs(float(lm["tipL"][0] - lm["cx"])) < 0.12 * H or abs(float(lm["tipR"][0] - lm["cx"])) < 0.12 * H:
        if max(dL, dR) < 70:
            raise FitRejected("could not find both arms out to the side. Export a full-body T-pose or A-pose.", info)
    # legs: a deep knee bend is not a standing bind pose
    leg = _drop(lm["hipL"], lm["kL"])
    info["thigh_drop"] = round(leg, 2)
    if leg < 50:
        raise FitRejected("the legs are bent (a sit or a kneel). Export a standing T-pose or A-pose.", info)
    mean_d = 0.5 * (dL + dR)
    mean_f = 0.5 * (fL + fR)
    if mean_d < 18:
        kind = "T"
    elif mean_d <= 75:
        kind = "A"
    else:
        kind = "down"
    need = abs(mean_d - tmpl["arm_drop"]) > 12 or abs(mean_f - tmpl["arm_fwd"]) > 0.22
    info["pose"] = kind
    info["warp_arms"] = bool(need)
    return info


_POINT_KEYS = ("pelvis", "head", "shL", "shR", "eL", "eR", "wL", "wR", "tipL", "tipR",
               "hipL", "hipR", "kL", "kR", "aL", "aR")


def place_on_template(V, lm, tmpl):
    """Metres, feet on the template sole, spine under the template pelvis, height matched."""
    ymin = float(V[:, 1].min())
    H = float(V[:, 1].max() - ymin)
    s = float(tmpl["height"] / max(H, 1e-8))
    cx, cz = float(lm["cx"]), float(lm["cz"])
    origin = np.array([cx, ymin, cz], float)
    dest = np.array([tmpl["joints"][tmpl["index"]["pelvis"]][0], tmpl["ymin"], tmpl["joints"][tmpl["index"]["pelvis"]][2]], float)

    def xf(P):
        return (np.asarray(P, float) - origin) * s + dest

    V2 = xf(V)
    lm2 = dict(lm)
    for k in _POINT_KEYS:
        if k in lm2 and isinstance(lm2[k], np.ndarray):
            lm2[k] = xf(lm2[k])
    lm2["H"] = float(tmpl["height"])
    lm2["ymin"] = float(tmpl["ymin"])
    lm2["half"] = float(lm.get("half", 0.12) * s)
    lm2["cx"] = float(dest[0]); lm2["cz"] = float(dest[2])
    return V2, lm2, s


def _bone_deform(V, p0, p1, q0, q1):
    sd = np.asarray(p1, float) - np.asarray(p0, float)
    dd = np.asarray(q1, float) - np.asarray(q0, float)
    sl = np.linalg.norm(sd) + 1e-12
    dl = np.linalg.norm(dd) + 1e-12
    sh = sd / sl
    R = _rot_between(sd, dd)
    along = (V - p0) @ sh
    perp = (V - p0) - along[:, None] * sh
    spun = (R @ (perp + (along * (dl / sl))[:, None] * sh).T).T
    return np.asarray(q0, float) + spun


def _ss(t, a, b):
    x = np.clip((t - a) / (b - a + 1e-12), 0.0, 1.0)
    return x * x * (3.0 - 2.0 * x)


def warp_arms(V, lm, tmpl):
    """Rotate a straight T / coronal A / arms-down pose onto the template's bent A-pose arms."""
    X = np.array(V, float, copy=True)
    P = tmpl["joints"]; idx = tmpl["index"]
    d_spine, _ = _seg_dist(V, lm["pelvis"], lm["head"])
    for side, sL, wL, tL, sign in (("l", "shL", "wL", "tipL", 1), ("r", "shR", "wR", "tipR", -1)):
        u = P[idx["upperarm_" + side]]; e = P[idx["lowerarm_" + side]]; h = P[idx["hand_" + side]]
        sh = lm[sL]; wr = lm[wL]
        tip = lm[tL] if tL in lm else wr
        arm_len = np.linalg.norm(tip - sh) + 1e-12
        upper_len = np.linalg.norm(e - u); fore_len = np.linalg.norm(h - e)
        if "e" + ("L" if sign > 0 else "R") in lm and isinstance(lm.get("e" + ("L" if sign > 0 else "R")), np.ndarray):
            e_src = lm["e" + ("L" if sign > 0 else "R")]
            w_src = wr
            extra = max(0.0, np.linalg.norm(tip - w_src))
        else:
            scale = min(1.0, arm_len / (upper_len + fore_len))
            e_src = sh + (tip - sh) * (upper_len * scale / arm_len)
            w_src = sh + (tip - sh) * ((upper_len + fore_len) * scale / arm_len)
            extra = max(0.0, arm_len - (upper_len + fore_len) * scale)
        hd = h - e
        hd = hd / (np.linalg.norm(hd) + 1e-12)
        tip_t = h + hd * extra
        d, t = _seg_dist(V, sh, tip)
        arm = (d < d_spine) & (d < 0.11 * lm["H"]) & (t > -0.05) & (t < 1.15) & ((V[:, 0] - lm["cx"]) * sign > -0.02 * lm["H"])
        if arm.sum() < 4:
            continue
        p_up = _bone_deform(V, sh, e_src, u, e)
        p_fo = _bone_deform(V, e_src, w_src, e, h)
        p_fi = _bone_deform(V, w_src, tip, h, tip_t)
        tu = float(np.linalg.norm(e_src - sh) / arm_len)
        tw = float(np.linalg.norm(w_src - sh) / arm_len)
        wu = _ss(t, tu - 0.08, tu + 0.02)
        wf = _ss(t, tw - 0.08, tw + 0.02)
        p = (1 - wu)[:, None] * p_up + wu[:, None] * p_fo
        p = (1 - wf)[:, None] * p + wf[:, None] * p_fi
        wa = _ss(t, 0.00, 0.18)
        p = (1 - wa)[:, None] * V + wa[:, None] * p
        X[arm] = p[arm]
    return X


# ---------------------------------------------------------------- weight transfer
def _tri_adj(F, nv):
    buckets = [[] for _ in range(nv)]
    for fi, f in enumerate(F):
        for k in (0, 1, 2):
            buckets[int(f[k])].append(fi)
    return buckets


def _closest_on_triangles(p, A, B, C):
    """Closest point of one query against many triangles. Returns barycentric (A,B,C) and distance squared."""
    AB = B - A; AC = C - A; AP = p - A
    d1 = (AB * AP).sum(-1); d2 = (AC * AP).sum(-1)
    BP = p - B; d3 = (AB * BP).sum(-1); d4 = (AC * BP).sum(-1)
    CP = p - C; d5 = (AB * CP).sum(-1); d6 = (AC * CP).sum(-1)
    vc = d1 * d4 - d3 * d2
    vb = d5 * d2 - d1 * d6
    va = d3 * d6 - d5 * d4
    n = len(A)
    bc = np.zeros((n, 3))
    m = (d1 <= 0) & (d2 <= 0); bc[m] = (1, 0, 0)
    m = (d3 >= 0) & (d4 <= d3); bc[m] = (0, 1, 0)
    m = (d6 >= 0) & (d5 <= d6); bc[m] = (0, 0, 1)
    m = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
    v = d1 / (d1 - d3 + 1e-18)
    bc[m, 0] = 1 - v[m]; bc[m, 1] = v[m]; bc[m, 2] = 0
    m = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
    w = d2 / (d2 - d6 + 1e-18)
    bc[m, 0] = 1 - w[m]; bc[m, 2] = w[m]; bc[m, 1] = 0
    m = (va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0)
    w = (d4 - d3) / ((d4 - d3) + (d5 - d6) + 1e-18)
    bc[m, 0] = 0; bc[m, 1] = 1 - w[m]; bc[m, 2] = w[m]
    denom = va + vb + vc
    inside = (va >= 0) & (vb >= 0) & (vc >= 0) & (denom > 1e-12)
    bc[inside, 0] = va[inside] / denom[inside]
    bc[inside, 1] = vb[inside] / denom[inside]
    bc[inside, 2] = vc[inside] / denom[inside]
    bc = np.clip(bc, 0, None)
    bc /= bc.sum(1, keepdims=True) + 1e-18
    pt = bc[:, 0:1] * A + bc[:, 1:2] * B + bc[:, 2:3] * C
    return bc, ((pt - p) ** 2).sum(-1)


def transfer_weights(Vq, tmpl, faces, smooth=4):
    """Nearest-surface barycentric weights, smoothed, then the top 4 influences renormalised."""
    TV, TF, TD = tmpl["V"], tmpl["F"], tmpl["dense"]
    adj = _tri_adj(TF, len(TV))
    nq = len(Vq)
    dense = np.zeros((nq, TD.shape[1]), np.float64)
    dist = np.empty(nq, np.float64)
    # float32 distances keep a 20k x 15k block under ~1 GB when chunked
    Vt = TV.astype(np.float32)
    k = 8
    for i0 in range(0, nq, 400):
        q = Vq[i0:i0 + 400].astype(np.float32)
        d2 = ((q[:, None, :] - Vt[None, :, :]) ** 2).sum(-1)
        nn = np.argpartition(d2, k, axis=1)[:, :k]
        for r in range(len(q)):
            cand = []
            for v in nn[r]:
                cand.extend(adj[int(v)])
            if not cand:
                dist[i0 + r] = 1.0
                dense[i0 + r, 0] = 1.0
                continue
            cand = list(set(cand))
            tri = TF[cand]
            bc, dd = _closest_on_triangles(Vq[i0 + r], TV[tri[:, 0]], TV[tri[:, 1]], TV[tri[:, 2]])
            t = int(np.argmin(dd))
            f = cand[t]
            dense[i0 + r] = bc[t, 0] * TD[TF[f, 0]] + bc[t, 1] * TD[TF[f, 1]] + bc[t, 2] * TD[TF[f, 2]]
            dist[i0 + r] = float(np.sqrt(dd[t]))
    if smooth and len(faces):
        e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
        e = np.concatenate([e, e[:, ::-1]])
        # drop edges that point at a removed vertex
        e = e[(e[:, 0] < nq) & (e[:, 1] < nq)]
        deg = np.bincount(e[:, 0], minlength=nq).astype(np.float64)
        for _ in range(int(smooth)):
            acc = np.zeros_like(dense)
            np.add.at(acc, e[:, 0], dense[e[:, 1]])
            dense = 0.65 * dense + 0.35 * acc / np.maximum(deg, 1.0)[:, None]
    s = dense.sum(1, keepdims=True); s[s == 0] = 1
    dense /= s
    top = np.argsort(-dense, axis=1)[:, :4]
    tw = np.take_along_axis(dense, top, 1)
    tw[tw < 0.02] = 0
    bad = tw.sum(1) < 1e-8
    if bad.any():
        tw[bad, 0] = 1.0
        top[bad, 0] = np.argmax(dense[bad], axis=1)
    tw /= np.maximum(tw.sum(1, keepdims=True), 1e-12)
    top = np.where(tw > 0, top, 0).astype(np.int32)
    return top, tw.astype(np.float32), dist


def _normals(V, F):
    N = np.zeros_like(V)
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    for k in range(3):
        np.add.at(N, F[:, k], fn)
    ln = np.linalg.norm(N, axis=1)
    N[ln < 1e-12] = (0.0, 1.0, 0.0)
    ln = np.linalg.norm(N, axis=1)
    return N / ln[:, None]


def _explode_uv(V, F, fuv, J, W, N):
    """One UV per vertex when every corner agrees; otherwise split the seams."""
    if fuv is None or len(fuv) != len(F):
        UV = np.zeros((len(V), 2), np.float32)
        span = np.ptp(V[:, :2], axis=0)
        span[span < 1e-8] = 1
        UV[:, 0] = (V[:, 0] - V[:, 0].min()) / span[0]
        UV[:, 1] = (V[:, 1] - V[:, 1].min()) / span[1]
        return V, F, UV, J, W, N, False
    vary = np.zeros(len(V))
    acc = np.zeros((len(V), 2)); cnt = np.zeros(len(V))
    for k in range(3):
        np.add.at(acc, F[:, k], fuv[:, k])
        np.add.at(cnt, F[:, k], 1)
    mean = acc / np.maximum(cnt, 1)[:, None]
    for k in range(3):
        d = np.linalg.norm(fuv[:, k] - mean[F[:, k]], axis=1)
        np.maximum.at(vary, F[:, k], d)
    if float(vary.max()) < 0.04:
        return V, F, mean.astype(np.float32), J, W, N, False
    P = V[F].reshape(-1, 3)
    UV = np.asarray(fuv, np.float32).reshape(-1, 2)
    JJ = J[F].reshape(-1, 4)
    WW = W[F].reshape(-1, 4)
    NN = N[F].reshape(-1, 3)
    FF = np.arange(len(P), dtype=np.int32).reshape(-1, 3)
    return P, FF, UV, JJ, WW, NN, True


# ---------------------------------------------------------------- fit
def _bone_landmarks(rig, rec, V):
    from .bonemap import index_map
    im = index_map(rig, rec)
    P = rig.bind[:, :3, 3]
    want = {"hips": "pelvis", "head": "head",
            "upperarm_L": "shL", "upperarm_R": "shR", "forearm_L": "eL", "forearm_R": "eR",
            "hand_L": "wL", "hand_R": "wR", "thigh_L": "hipL", "thigh_R": "hipR",
            "shin_L": "kL", "shin_R": "kR", "foot_L": "aL", "foot_R": "aR"}
    lm = {}
    for canon, key in want.items():
        i = im.get(canon)
        if i is not None and i >= 0:
            lm[key] = P[int(i)].astype(float).copy()
    if not all(k in lm for k in ("shL", "shR", "wL", "wR", "pelvis")):
        return None
    H = float(V[:, 1].ptp())
    for side, e, w in (("L", "eL", "wL"), ("R", "eR", "wR")):
        if e in lm:
            d = lm[w] - lm[e]
        else:
            d = lm[w] - lm["sh" + side]
        n = np.linalg.norm(d) + 1e-12
        lm["tip" + side] = lm[w] + d / n * (0.08 * H)
    lm["cx"] = float(lm["pelvis"][0]); lm["cz"] = float(lm["pelvis"][2])
    lm["H"] = H; lm["ymin"] = float(V[:, 1].min()); lm["half"] = abs(float(lm["shL"][0] - lm["cx"]))
    return lm


def orient_file(path):
    """Library ``orient=auto`` (Y-up, face +Z when the rig maps, metres, feet grounded), then a
    landmark fix for an unrigged mesh whose arm span was longer than its height."""
    from .importers import load_file
    report = {}
    rig, rec, report = load_file(path, report, orient="auto")
    if not rig.has_mesh():
        raise FitRejected("%s has no triangles" % os.path.basename(path))
    rigged = all(k in rec.get("map", {}) for k in ("hips", "upperarm_L", "hand_L", "upperarm_R", "hand_R"))
    notes = list(report.get("fixes") or [])
    lm = _bone_landmarks(rig, rec, rig.V) if rigged else None
    if lm is None:
        rig.V, extra = stand_mesh(rig.V, use_orient_fix=True)
        notes.extend(extra)
        rigged = False
    else:
        # orient already grounded a rigged mesh on its own bone. Keep that frame; placement
        # onto the template happens with the bone landmarks.
        notes.append("used the imported skeleton for landmarks (%s)" % rec.get("convention"))
    return rig, lm, notes, rec


def _chest_apex(V, sel):
    if sel.sum() < 12:
        return None
    return float(np.percentile(V[sel, 2], 95))


def flatten_male_chest(V, joints, names):
    """Pull the pointed front of each pec back toward the ribcage.

    The MakeHuman rest mesh is left-right symmetric. The apex still reads as a breast,
    and that is what showed on the right chest in game. Both sides are flattened the
    same way. This is a fit step, not a list of vertex indices for one file.
    """
    V = np.array(V, float, copy=True)
    sp = joints[names.index("spine_03")]
    band = ((np.abs(V[:, 0]) < 0.14) & (V[:, 1] > sp[1] + 0.04) & (V[:, 1] < sp[1] + 0.30)
            & (V[:, 2] > sp[2] + 0.04))
    before, after = {}, {}
    for sign, lab in ((1, "left"), (-1, "right")):
        sel = band & (V[:, 0] * sign > 0.02)
        before[lab] = _chest_apex(V, sel)
        if before[lab] is None:
            continue
        z = V[sel, 2]
        base = float(np.percentile(z, 30))
        V[sel, 2] = z - 0.85 * np.clip(z - base, 0, None)
        after[lab] = _chest_apex(V, sel)
    return V, {"before_p95_m": before, "after_p95_m": after}


def _elbow_inside(V, wf, E, au, af):
    crook = au + af
    n = np.linalg.norm(crook)
    if n < 1e-8:
        return np.zeros(len(V), bool), None
    crook = crook / n
    bend = np.cross(au, af)
    bn = np.linalg.norm(bend)
    if bn < 1e-8:
        return np.zeros(len(V), bool), None
    bend = bend / bn
    rel = V - E
    inside = (np.linalg.norm(rel, axis=1) < 0.065) & ((rel @ crook) > 0.0) & (wf > 0.12) & (wf < 0.88)
    return inside, bend


def _bend_radius(V, E, bend, mask, wf, ang):
    ca, sa = np.cos(ang), np.sin(ang)
    rel = V - E
    swung = rel * ca + np.cross(bend, rel) * sa + np.outer(rel @ bend, bend) * (1 - ca)
    posed = (1 - wf)[:, None] * V + wf[:, None] * (E + swung)
    r = posed - E
    along = r @ bend
    return np.linalg.norm(r - along[:, None] * bend, axis=1)[mask]


def preserve_elbows(V, J, W, joints, names, bend_deg=100.0):
    """Rest-pose radial correction so a hard elbow bend keeps its cross-section under linear blend skinning.

    The game only has linear blend skinning. A 100 degree bend (a carry, a catch) otherwise
    pinches the inner elbow. Three small outward steps on the rest mesh recover that radius.
    """
    V = np.array(V, float, copy=True)
    ang = np.radians(bend_deg)
    stats = {}
    for side in ("l", "r"):
        fore = [i for i, n in enumerate(names) if n.endswith("_" + side) and n.startswith(
            ("lowerarm", "hand", "index", "middle", "pinky", "ring", "thumb"))]
        if "lowerarm_" + side not in names:
            continue
        wf = np.zeros(len(V))
        fore_a = np.array(fore, int)
        for k in range(4):
            wf += W[:, k] * np.isin(J[:, k], fore_a)
        E = joints[names.index("lowerarm_" + side)]
        U = joints[names.index("upperarm_" + side)]
        H = joints[names.index("hand_" + side)]
        au = U - E; af = H - E
        au = au / (np.linalg.norm(au) + 1e-12); af = af / (np.linalg.norm(af) + 1e-12)
        inside, bend = _elbow_inside(V, wf, E, au, af)
        if bend is None or inside.sum() < 8:
            continue
        rest = np.linalg.norm((V - E) - np.outer((V - E) @ bend, bend), axis=1)
        before = _bend_radius(V, E, bend, inside, wf, ang)
        target = rest[inside]
        for _ in range(3):
            now = _bend_radius(V, E, bend, inside, wf, ang)
            deficit = np.clip(target - now, 0, 0.012)
            rel = V[inside] - E
            along = rel @ bend
            radial = rel - along[:, None] * bend
            ln = np.linalg.norm(radial, axis=1, keepdims=True)
            radial = np.where(ln > 1e-6, radial / np.maximum(ln, 1e-6), 0)
            V[inside] += radial * deficit[:, None] * 0.85
        after = _bend_radius(V, E, bend, inside, wf, ang)
        stats[side] = {
            "before_ratio": round(float(np.mean(before / np.maximum(target, 1e-4))), 3),
            "after_ratio": round(float(np.mean(after / np.maximum(target, 1e-4))), 3),
            "verts": int(inside.sum()),
        }
    return V, stats


def finger_pad(V, J, W, names, joints):
    """How far the mesh sticks past the last finger bone, along that bone. Metres."""
    pads = []
    for n in names:
        if not (n.endswith("_03_l") or n.endswith("_03_r")):
            continue
        parent = n.replace("_03", "_02")
        if parent not in names:
            continue
        i = names.index(n)
        w = np.zeros(len(V))
        for k in range(4):
            w += W[:, k] * (J[:, k] == i)
        sel = w > 0.5
        if sel.sum() < 4:
            continue
        A = joints[names.index(parent)]; B = joints[i]
        direction = B - A
        direction = direction / (np.linalg.norm(direction) + 1e-12)
        along = (V[sel] - B) @ direction
        pads.append(float(np.percentile(along, 90)))
    if not pads:
        return 0.02
    return float(np.clip(np.median(pads), 0.0, 0.045))


def grip_clearance(pad):
    """Bone targets must sit this far outside the ball centre so the skin is still 1.2 cm clear.

    The game's outsideBall already keeps the bone 1.2 cm off a 0.11 m ball. The fingertip
    mesh continues past that bone, which is why the fingers sank into the leather.
    """
    clearance = 0.012 + float(pad)
    return float(np.clip(clearance, 0.012, 0.06)), {
        "pad_m": round(float(pad), 4),
        "clearance_m": round(float(np.clip(clearance, 0.012, 0.06)), 4),
        "penetration_before_m": round(float(pad - 0.012), 4),
        "clearance_after_m": 0.012,
        "ball_radius_m": 0.11,
    }


def _face_bone(F, J, W, nb):
    acc = np.zeros((len(F), nb), np.float64)
    ii = np.arange(len(F))
    for k in range(3):
        for c in range(4):
            np.add.at(acc, (ii, np.clip(J[F[:, k], c], 0, nb - 1)), W[F[:, k], c])
    return np.argmax(acc, 1)


def _submesh(V, F, J, W, N, faces):
    used = np.unique(F[faces])
    remap = -np.ones(len(V), np.int32)
    remap[used] = np.arange(len(used), dtype=np.int32)
    return V[used].copy(), remap[F[faces]], J[used].copy(), W[used].copy(), N[used].copy()


def sample_uv(Vq, tmpl):
    """Barycentric template UVs at the nearest surface point. Used to land kit shells on the squad atlas."""
    TV, TF, UV = tmpl["V"], tmpl["F"], tmpl["UV"]
    adj = _tri_adj(TF, len(TV))
    out = np.zeros((len(Vq), 2), np.float64)
    Vt = TV.astype(np.float32)
    k = 8
    for i0 in range(0, len(Vq), 400):
        q = Vq[i0:i0 + 400].astype(np.float32)
        d2 = ((q[:, None, :] - Vt[None, :, :]) ** 2).sum(-1)
        nn = np.argpartition(d2, min(k, d2.shape[1] - 1), axis=1)[:, :k]
        for r in range(len(q)):
            cand = []
            for v in nn[r]:
                cand.extend(adj[int(v)])
            if not cand:
                continue
            cand = list(set(cand))
            tri = TF[cand]
            bc, dd = _closest_on_triangles(Vq[i0 + r], TV[tri[:, 0]], TV[tri[:, 1]], TV[tri[:, 2]])
            t = int(np.argmin(dd))
            f = cand[t]
            out[i0 + r] = bc[t, 0] * UV[TF[f, 0]] + bc[t, 1] * UV[TF[f, 1]] + bc[t, 2] * UV[TF[f, 2]]
    return out


def split_kit(V, F, J, W, N, tmpl, uv=None):
    """Body mesh plus jersey / shorts / socks / boots shells whose UVs sit on the squad kit atlas.

    Left half of kit_*.png is jersey, socks and boots. Right half is shorts. The game
    replaces the texture on every mesh tagged kit in the .parts file.
    """
    from .mhchar import kit_uv
    names = tmpl["names"]
    P = tmpl["joints"]
    bone = _face_bone(F, J, W, len(names))
    nm = np.array(names)[bone]
    cen = V[F].mean(1)
    y = cen[:, 1]
    jersey = (np.char.startswith(nm, "spine_") | np.isin(nm, ["clavicle_l", "clavicle_r", "neck_01"])
              | ((nm == "pelvis") & (y > 1.02)))
    jersey |= np.isin(nm, ["upperarm_l", "upperarm_r"]) & (cen[:, 1] > 1.15)
    shorts = (nm == "pelvis") | np.isin(nm, ["thigh_l", "thigh_r"])
    shorts &= y < 1.05
    socks = np.isin(nm, ["calf_l", "calf_r"]) & (y < 0.42) & (y > 0.12)
    boots = np.isin(nm, ["foot_l", "foot_r", "ball_l", "ball_r"]) | (np.isin(nm, ["calf_l", "calf_r"]) & (y < 0.16))
    role = np.full(len(F), "body", object)
    role[jersey] = "jersey"
    role[shorts] = "shorts"
    role[socks] = "socks"
    role[boots] = "boots"
    parts = []

    class _P:
        pass

    body = _P()
    body.name, body.role, body.image = "body", "body", "skin"
    body.V, body.F, body.J, body.W, body.N = V, F, J, W, N
    if uv is not None and len(uv) == len(V):
        body.UV = np.asarray(uv, np.float32)
    else:
        body.UV = np.zeros((len(V), 2), np.float32)
        span = np.ptp(V[:, :2], axis=0); span[span < 1e-6] = 1
        body.UV[:, 0] = ((V[:, 0] - V[:, 0].min()) / span[0]).astype(np.float32)
        body.UV[:, 1] = ((V[:, 1] - V[:, 1].min()) / span[1]).astype(np.float32)
    body.C = None
    parts.append(body)
    report = []
    for gname in ("jersey", "shorts", "socks", "boots"):
        faces = np.nonzero(role == gname)[0]
        if len(faces) < 8:
            continue
        sv, sf, sj, sw, sn = _submesh(V, F, J, W, N, faces)
        sn = sn.copy()
        ln = np.linalg.norm(sn, axis=1, keepdims=True)
        sv = sv + np.where(ln > 1e-6, sn / np.maximum(ln, 1e-6), 0) * 0.004
        uv = kit_uv(gname, sample_uv(sv, tmpl)).astype(np.float32)
        p = _P()
        p.name, p.role, p.image = gname, "kit", "kit"
        p.V, p.F, p.J, p.W, p.N, p.UV, p.C = sv.astype(np.float32), sf, sj, sw, sn.astype(np.float32), uv, None
        parts.append(p)
        report.append({"name": gname, "tris": int(len(sf)),
                       "u_min": round(float(uv[:, 0].min()), 3), "u_max": round(float(uv[:, 0].max()), 3)})
    return parts, report


def fit_arrays(V, F, tmpl, fuv=None, landmarks=None, orient_notes=None, smooth=4, stand=True):
    V = np.asarray(V, float)
    F = np.asarray(F, np.int32)
    notes = list(orient_notes or [])
    if landmarks is None and stand:
        V, extra = stand_mesh(V, True)
        notes.extend(extra)
        lm = estimate_landmarks(V)
    elif landmarks is None:
        lm = estimate_landmarks(V)
    else:
        lm = dict(landmarks)
        geo = estimate_landmarks(V)
        for k, val in geo.items():
            lm.setdefault(k, val)
    info = classify_pose(lm, tmpl)
    V, lm, scale = place_on_template(V, lm, tmpl)
    if info["warp_arms"]:
        V = warp_arms(V, lm, tmpl)
    V, chest = flatten_male_chest(V, tmpl["joints"], tmpl["names"])
    # drop degenerate faces so they do not pollute the smooth
    area = np.linalg.norm(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]]), axis=1)
    keep = area > 1e-12
    F = F[keep]
    if fuv is not None:
        fuv = np.asarray(fuv, float)[keep]
    J, W, dist = transfer_weights(V, tmpl, F, smooth=smooth)
    V, elbow = preserve_elbows(V, J, W, tmpl["joints"], tmpl["names"])
    N = _normals(V, F)
    V, F, UV, J, W, N, seams = _explode_uv(V, F, fuv, J, W, N)
    far = float((dist > 0.08 * tmpl["height"]).mean()) if len(dist) else 0.0
    wsum = W.sum(1)
    report = {
        "pose": info["pose"], "warp_arms": info["warp_arms"], "pose_detail": info,
        "scale": round(float(scale), 4), "orientation": notes, "uv_seams_split": seams,
        "tris": int(len(F)), "verts": int(len(V)),
        "weight_sum_min": round(float(wsum.min()), 5), "weight_sum_max": round(float(wsum.max()), 5),
        "max_influences": int((W > 1e-4).sum(1).max()) if len(W) else 0,
        "unweighted": int((wsum < 1e-5).sum()),
        "surface_dist_mean_m": round(float(dist.mean()), 4),
        "surface_dist_p90_m": round(float(np.percentile(dist, 90)), 4),
        "far_fraction": round(far, 4),
        "poly_warning": int(len(F)) > 22000,
        "chest": chest,
        "elbow": elbow,
    }
    return {"V": V.astype(np.float32), "N": N.astype(np.float32), "UV": UV, "F": F, "J": J, "W": W, "report": report, "dist": dist}


def arms_to_tpose(V, joints, names):
    """Straighten the template's bent arms out along +X. Test and preview fixture only.

    The result is a T-pose of the CC0 template body, not a photograph and not a generated person.
    """
    idx = {n: i for i, n in enumerate(names)}
    X = np.array(V, float, copy=True)
    for side, sign in (("l", 1.0), ("r", -1.0)):
        u = joints[idx["upperarm_" + side]]; e = joints[idx["lowerarm_" + side]]; h = joints[idx["hand_" + side]]
        eT = u + np.array([sign * np.linalg.norm(e - u), 0, 0])
        hT = eT + np.array([sign * np.linalg.norm(h - e), 0, 0])
        d_ue, _ = _seg_dist(V, u, e)
        d_eh, _ = _seg_dist(V, e, h)
        arm = (np.minimum(d_ue, d_eh) < 0.11) & ((V[:, 0] - u[0]) * sign > -0.02)
        p_up = _bone_deform(V, u, e, u, eT)
        p_fo = _bone_deform(V, e, h, eT, hT)
        use_fore = d_eh < d_ue
        P = np.where(use_fore[:, None], p_fo, p_up)
        near = np.abs(d_ue - d_eh) < 0.04
        P = np.where(near[:, None], 0.5 * (p_up + p_fo), P)
        X[arm] = P[arm]
    return X


# ---------------------------------------------------------------- skinning check (the game's linear blend, on the CPU)
def _parents(doc):
    parent = np.full(len(doc["nodes"]), -1, np.int32)
    for i, nd in enumerate(doc["nodes"]):
        for c in nd.get("children", []):
            parent[c] = i
    return parent


def _topo(parent):
    order = []
    seen = set()
    def visit(i):
        if i in seen:
            return
        if parent[i] >= 0:
            visit(int(parent[i]))
        seen.add(i); order.append(i)
    for i in range(len(parent)):
        visit(i)
    return order


def _sample(times, values, t):
    if t <= times[0]:
        return values[0]
    if t >= times[-1]:
        return values[-1]
    i = int(np.searchsorted(times, t, side="right") - 1)
    i = max(0, min(i, len(times) - 2))
    u = float((t - times[i]) / (times[i + 1] - times[i] + 1e-12))
    a, b = values[i], values[i + 1]
    if a.shape[-1] == 4:
        if float(np.dot(a, b)) < 0:
            b = -b
        q = (1 - u) * a + u * b
        return q / (np.linalg.norm(q) + 1e-12)
    return (1 - u) * a + u * b


def skin_frame(doc, buf, V, J, W, clip, t_frac):
    """Linear-blend skinning at a fraction of one clip. This is the same blend the game's CPU
    path writes into the vertex buffer and the GPU path applies from the bone matrices."""
    from .rigrec import mats_from_quat
    names = [n.get("name", "") for n in doc["nodes"]]
    anim = next(a for a in doc["animations"] if a.get("name") == clip)
    base = []
    for nd in doc["nodes"]:
        T = np.array(nd.get("translation", [0, 0, 0]), float)
        R = np.array(nd.get("rotation", [0, 0, 0, 1]), float)
        S = np.array(nd.get("scale", [1, 1, 1]), float)
        base.append([T, R, S])
    # duration
    dur = 0.0
    channels = []
    for ch in anim["channels"]:
        sm = anim["samplers"][ch["sampler"]]
        times = _acc_bytes_np(doc, buf, sm["input"]).reshape(-1)
        values = _acc_bytes_np(doc, buf, sm["output"])
        ncomp = values.size // max(len(times), 1)
        values = values.reshape(len(times), ncomp)
        dur = max(dur, float(times[-1]) if len(times) else 0.0)
        channels.append((ch, times, values))
    t = float(np.clip(t_frac, 0, 1) * dur)
    TRS = [[b[0].copy(), b[1].copy(), b[2].copy()] for b in base]
    for ch, times, values in channels:
        if len(times) == 0:
            continue
        val = _sample(times, values, t)
        ni = ch["target"]["node"]; path = ch["target"]["path"]
        if path == "translation":
            TRS[ni][0] = val
        elif path == "rotation":
            TRS[ni][1] = val
        elif path == "scale":
            TRS[ni][2] = val
    parent = _parents(doc)
    local = []
    for T, R, S in TRS:
        M = np.eye(4)
        M[:3, :3] = mats_from_quat(R) * np.asarray(S, float)[None, :]
        M[:3, 3] = T
        local.append(M)
    world = [None] * len(local)
    for i in _topo(parent):
        world[i] = local[i] if parent[i] < 0 else world[parent[i]] @ local[i]
    sk = doc["skins"][0]
    ibm = np.frombuffer(_acc_bytes(doc, buf, sk["inverseBindMatrices"]), np.float32).reshape(-1, 4, 4).transpose(0, 2, 1).astype(np.float64)
    joint_nodes = sk["joints"]
    skin = np.stack([world[n] @ ibm[k] for k, n in enumerate(joint_nodes)])
    out = np.zeros((len(V), 3), np.float64)
    vh = np.c_[np.asarray(V, float), np.ones(len(V))]
    J = np.asarray(J, np.int32); W = np.asarray(W, float)
    for k in range(4):
        wk = W[:, k]
        if not np.any(wk):
            continue
        M = skin[J[:, k]]
        out += wk[:, None] * np.einsum("nij,nj->ni", M, vh)[:, :3]
    joint_pos = np.stack([world[n][:3, 3] for n in joint_nodes])
    return out, joint_pos, dur


def _acc_bytes_np(doc, buf, index):
    acc = doc["accessors"][index]
    raw = _acc_bytes(doc, buf, index)
    dt = {5126: np.float32, 5123: np.uint16, 5121: np.uint8, 5125: np.uint32}[acc["componentType"]]
    return np.frombuffer(raw, dtype=dt).astype(np.float64)


def deform_report(glb_path):
    doc, buf = _read(glb_path)
    pr = doc["meshes"][0]["primitives"][0]
    V = np.frombuffer(_acc_bytes(doc, buf, pr["attributes"]["POSITION"]), np.float32).astype(np.float64).reshape(-1, 3)
    jc = doc["accessors"][pr["attributes"]["JOINTS_0"]]["componentType"]
    J = np.frombuffer(_acc_bytes(doc, buf, pr["attributes"]["JOINTS_0"]), {5121: np.uint8, 5123: np.uint16}[jc]).astype(np.int32).reshape(-1, 4)
    W = np.frombuffer(_acc_bytes(doc, buf, pr["attributes"]["WEIGHTS_0"]), np.float32).astype(np.float64).reshape(-1, 4)
    # stride a dense mesh; the flags are about the body, not every seam copy
    step = max(1, len(V) // 6000)
    Vs, Js, Ws = V[::step], J[::step], W[::step]
    rest_h = float(np.percentile(Vs[:, 1], 99) - Vs[:, 1].min())
    dom = Js[np.arange(len(Js)), np.argmax(Ws, axis=1)]
    # bind joint positions
    sk = doc["skins"][0]
    ibm = np.frombuffer(_acc_bytes(doc, buf, sk["inverseBindMatrices"]), np.float32).reshape(-1, 4, 4).transpose(0, 2, 1)
    bind = np.linalg.inv(ibm.astype(np.float64))[:, :3, 3]
    rest_d = np.linalg.norm(Vs - bind[dom], axis=1) + 1e-4
    flags = []
    clips = {}
    have = {a.get("name") for a in doc.get("animations", [])}
    for name in CLIP_CHECK:
        if name not in have:
            flags.append("missing clip %s" % name)
            continue
        samples = []
        for frac in (0.15, 0.50, 0.85):
            posed, jpos, dur = skin_frame(doc, buf, Vs, Js, Ws, name, frac)
            h = float(np.percentile(posed[:, 1], 99) - posed[:, 1].min())
            travel = float(np.linalg.norm(posed - Vs, axis=1).max())
            pose_d = np.linalg.norm(posed - jpos[dom], axis=1) + 1e-4
            ratio = pose_d / rest_d
            samples.append({"t": frac, "height_m": round(h, 3), "max_travel_m": round(travel, 3),
                            "bone_dist_ratio_median": round(float(np.median(ratio)), 3),
                            "bone_dist_ratio_p95": round(float(np.percentile(ratio, 95)), 3)})
            if travel > 2.5:
                flags.append("%s t=%.2f vertex travelled %.2f m (explosion)" % (name, frac, travel))
            if name == "idle" and h < 0.55 * rest_h:
                flags.append("idle height collapsed to %.2f m (rest %.2f m)" % (h, rest_h))
            if float(np.median(ratio)) > 1.8 or float(np.percentile(ratio, 95)) > 3.0:
                flags.append("%s t=%.2f bone-distance ratio median %.2f p95 %.2f (candy-wrap or balloon)" % (
                    name, frac, float(np.median(ratio)), float(np.percentile(ratio, 95))))
        clips[name] = samples
    return {"rest_height_m": round(rest_h, 3), "clips": clips, "flags": flags}


def _mesh_arrays(doc, buf, prim):
    V = np.frombuffer(_acc_bytes(doc, buf, prim["attributes"]["POSITION"]), np.float32).astype(np.float64).reshape(-1, 3)
    N = np.frombuffer(_acc_bytes(doc, buf, prim["attributes"]["NORMAL"]), np.float32).astype(np.float64).reshape(-1, 3)
    UV = np.frombuffer(_acc_bytes(doc, buf, prim["attributes"]["TEXCOORD_0"]), np.float32).astype(np.float64).reshape(-1, 2)
    return V, N, UV


def render_kits(glb_path, out_dir):
    """Front views with kit_home.png and kit_away.png on the kit shells. Proves the atlas swap."""
    from PIL import Image
    root = gaelic_clip._repo_root()
    if not root:
        return None
    texdir = os.path.join(root, "Gaelic_Football_3d", "assets", "textures")
    doc, buf = _read(glb_path)
    meshes = []
    for i, mesh in enumerate(doc.get("meshes", [])):
        pr = mesh["primitives"][0]
        V, N, UV = _mesh_arrays(doc, buf, pr)
        meshes.append((mesh.get("name", "m%d" % i), V, N, UV))
    if not meshes:
        return None
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    # one frame for both kits so the difference is the texture, not the pose
    body_col = np.array([196, 150, 120])
    for kit in ("home", "away"):
        atlas = np.asarray(Image.open(os.path.join(texdir, "kit_%s.png" % kit)).convert("RGB"))
        h, w = atlas.shape[:2]
        acc_v, acc_c, acc_n = [], [], []
        for name, V, N, UV in meshes:
            step = max(1, len(V) // 4000)
            Vs, Ns, UVs = V[::step], N[::step], UV[::step]
            if name == "body":
                col = np.tile(body_col, (len(Vs), 1))
            else:
                x = np.clip((UVs[:, 0] * (w - 1)).astype(int), 0, w - 1)
                y = np.clip(((1 - UVs[:, 1]) * (h - 1)).astype(int), 0, h - 1)
                col = atlas[y, x]
            acc_v.append(Vs); acc_c.append(col); acc_n.append(Ns)
        V = np.concatenate(acc_v); C = np.concatenate(acc_c); N = np.concatenate(acc_n)
        xy, z = _view_xy(V, "front")
        project = _projector((xy.min(0), xy.max(0)), (240, 400))
        px, py = project(xy)
        shade = np.clip(N @ np.array([0.15, 0.55, 0.75]), 0.35, 1.0)
        col = np.clip(C * shade[:, None], 0, 255).astype(np.uint8)
        Wd, Hd = 240, 400
        zbuf = np.full((Hd, Wd), -1e9)
        img = np.zeros((Hd, Wd, 3), np.uint8); img[:] = (18, 22, 28)
        xi = np.clip(px.astype(int), 0, Wd - 1); yi = np.clip(py.astype(int), 0, Hd - 1)
        for i in np.argsort(z):
            x, y = int(xi[i]), int(yi[i])
            if z[i] >= zbuf[y, x]:
                zbuf[y, x] = z[i]; img[y, x] = col[i]
        im = Image.fromarray(img, "RGB")
        dest = os.path.join(out_dir, "kit_%s.png" % kit)
        im.save(dest)
        paths.append(dest)
    a = np.asarray(Image.open(paths[0])); b = np.asarray(Image.open(paths[1]))
    return {"home": paths[0], "away": paths[1], "mean_abs_diff": round(float(np.abs(a.astype(int) - b.astype(int)).mean()), 2)}


def render_previews(glb_path, out_dir):
    """Front and side frames of the check clips, software-rasterised. Not the game window."""
    from PIL import Image, ImageDraw
    os.makedirs(out_dir, exist_ok=True)
    doc, buf = _read(glb_path)
    pr = doc["meshes"][0]["primitives"][0]
    V = np.frombuffer(_acc_bytes(doc, buf, pr["attributes"]["POSITION"]), np.float32).astype(np.float64).reshape(-1, 3)
    N = np.frombuffer(_acc_bytes(doc, buf, pr["attributes"]["NORMAL"]), np.float32).astype(np.float64).reshape(-1, 3)
    jc = doc["accessors"][pr["attributes"]["JOINTS_0"]]["componentType"]
    J = np.frombuffer(_acc_bytes(doc, buf, pr["attributes"]["JOINTS_0"]), {5121: np.uint8, 5123: np.uint16}[jc]).astype(np.int32).reshape(-1, 4)
    W = np.frombuffer(_acc_bytes(doc, buf, pr["attributes"]["WEIGHTS_0"]), np.float32).astype(np.float64).reshape(-1, 4)
    step = max(1, len(V) // 8000)
    frames = [("rest", V, None)]
    for name, frac in (("idle", 0.4), ("run", 0.35), ("kick_run", 0.45), ("catch", 0.55), ("solo", 0.4)):
        posed, jpos, _ = skin_frame(doc, buf, V, J, W, name, frac)
        frames.append((name, posed, jpos))
    tiles = []
    for name, posed, jpos in frames:
        for view in ("front", "side"):
            xy, _z = _view_xy(posed, view)
            bounds = (xy.min(0), xy.max(0))
            img, project = _splat(posed[::step], N[::step], view, bounds=bounds)
            if jpos is not None:
                _draw_bones(img, jpos, doc, view, project)
            dr = ImageDraw.Draw(img)
            dr.text((6, 4), "%s %s" % (name, view), fill=(255, 255, 255))
            tiles.append(img)
    w, h = tiles[0].size
    sheet = Image.new("RGB", (w * 2, h * len(frames)), (18, 22, 28))
    for i, im in enumerate(tiles):
        sheet.paste(im, ((i % 2) * w, (i // 2) * h))
    dest = os.path.join(out_dir, "deform_sheet.png")
    sheet.save(dest)
    return dest


def _view_xy(V, view):
    if view == "front":
        return V[:, [0, 1]], V[:, 2]
    return V[:, [2, 1]], -V[:, 0]


def _projector(bounds, size):
    """Shared by the mesh splat and the bone overlay so they sit on the same frame."""
    W, H = size
    mn, mx = bounds
    span = np.maximum(mx - mn, 1e-4)
    s = min((H - 16) / span[1], (W - 16) / span[0])

    def project(xy):
        px = (xy[:, 0] - mn[0]) * s + (W - span[0] * s) * 0.5
        py = H - 8 - (xy[:, 1] - mn[1]) * s
        return px, py

    return project


def _splat(V, N, view, size=(200, 340), bounds=None):
    from PIL import Image, ImageFilter
    W, H = size
    xy, z = _view_xy(V, view)
    if bounds is None:
        bounds = (xy.min(0), xy.max(0))
    project = _projector(bounds, size)
    px, py = project(xy)
    light = np.array([0.2, 0.6, 0.8]) if view == "front" else np.array([0.4, 0.7, 0.5])
    shade = np.clip(N @ (light / (np.linalg.norm(light) + 1e-12)), 0, 1)
    col = (40 + 180 * shade).astype(np.int32)
    zbuf = np.full((H, W), -1e9)
    img = np.zeros((H, W, 3), np.uint8)
    img[:] = (18, 22, 28)
    xi = np.clip(px.astype(int), 0, W - 1); yi = np.clip(py.astype(int), 0, H - 1)
    order = np.argsort(z)  # far first
    for i in order:
        x, y = int(xi[i]), int(yi[i])
        if z[i] >= zbuf[y, x]:
            zbuf[y, x] = z[i]
            img[y, x] = col[i]
    return Image.fromarray(img, "RGB").filter(ImageFilter.MaxFilter(3)), project


def _draw_bones(img, jpos, doc, view, project):
    from PIL import ImageDraw
    sk = doc["skins"][0]
    parent = _parents(doc)
    jn = sk["joints"]
    xy, _z = _view_xy(jpos, view)
    px, py = project(xy)
    dr = ImageDraw.Draw(img)
    jset = set(int(n) for n in jn)
    for k, n in enumerate(jn):
        p = int(parent[n])
        while p >= 0 and p not in jset:
            p = int(parent[p])
        if p < 0:
            continue
        b = list(jn).index(p)
        dr.line((float(px[k]), float(py[k]), float(px[b]), float(py[b])), fill=(255, 210, 80), width=1)


# ---------------------------------------------------------------- procedural fixture (CC0, this repo, no photograph)
def _box(center, size):
    c = np.asarray(center, float); h = np.asarray(size, float) / 2
    xs = np.array([-1, 1, 1, -1, -1, 1, 1, -1], float)
    ys = np.array([-1, -1, 1, 1, -1, -1, 1, 1], float)
    zs = np.array([-1, -1, -1, -1, 1, 1, 1, 1], float)
    V = np.stack([c[0] + xs * h[0], c[1] + ys * h[1], c[2] + zs * h[2]], 1)
    F = np.array([[0, 1, 2], [0, 2, 3], [4, 6, 5], [4, 7, 6],
                  [0, 4, 5], [0, 5, 1], [1, 5, 6], [1, 6, 2],
                  [2, 6, 7], [2, 7, 3], [3, 7, 4], [3, 4, 0]], np.int32)
    return V, F


def _segment_box(p0, p1, radius):
    p0 = np.asarray(p0, float); p1 = np.asarray(p1, float)
    d = p1 - p0
    length = np.linalg.norm(d) + 1e-12
    R = _rot_between(np.array([1.0, 0, 0]), d)
    V, F = _box([0, 0, 0], [length, radius * 2, radius * 2])
    V = V @ R.T + (p0 + p1) / 2
    return V, F


def procedural_humanoid(pose="T", up="Y", arm_span=1.55):
    """A box humanoid in metres, +Y up, facing +Z, left = +X. ``pose`` is T, A, or raised.

    Built from boxes in this file. No photograph, no scan, no third-party mesh.
    """
    parts = []
    parts.append(_box([0, 1.05, 0.02], [0.36, 0.55, 0.22]))          # torso
    parts.append(_box([0, 1.62, 0.03], [0.20, 0.26, 0.22]))          # head
    parts.append(_segment_box([0.09, 0.88, 0.0], [0.12, 0.48, 0.02], 0.07))
    parts.append(_segment_box([-0.09, 0.88, 0.0], [-0.12, 0.48, 0.02], 0.07))
    parts.append(_segment_box([0.12, 0.48, 0.02], [0.14, 0.08, 0.02], 0.055))
    parts.append(_segment_box([-0.12, 0.48, 0.02], [-0.14, 0.08, 0.02], 0.055))
    parts.append(_box([0.14, 0.045, 0.08], [0.09, 0.06, 0.24]))       # feet, toes +Z
    parts.append(_box([-0.14, 0.045, 0.08], [0.09, 0.06, 0.24]))
    shoulder = np.array([0.18, 1.38, 0.02])
    reach = arm_span * 0.5 - 0.18
    if pose == "T":
        direction = np.array([1.0, 0.0, 0.0])
    elif pose == "A":
        direction = np.array([0.75, -0.55, 0.28]); direction /= np.linalg.norm(direction)
    elif pose == "raised":
        direction = np.array([0.15, 1.0, 0.05]); direction /= np.linalg.norm(direction)
    else:
        raise ValueError(pose)
    for sign in (1.0, -1.0):
        d = direction * np.array([sign, 1, 1])
        if pose == "raised" and sign < 0:
            d = np.array([-1.0, 0.0, 0.0])  # only one arm up, so the pose is illegal
        a = shoulder * np.array([sign, 1, 1])
        elbow = a + d * reach * 0.48
        hand = a + d * reach
        parts.append(_segment_box(a, elbow, 0.045))
        parts.append(_segment_box(elbow, hand, 0.038))
    Vs, Fs = [], []
    off = 0
    for V, F in parts:
        Vs.append(V); Fs.append(F + off); off += len(V)
    V = np.concatenate(Vs); F = np.concatenate(Fs)
    if up == "Z":
        # Y-up -> Z-up (rotate +90 deg about X)
        R = _rot_between([0, 1, 0], [0, 0, 1])
        V = _apply_R(V, R)
    elif up != "Y":
        raise ValueError(up)
    return V, F


def write_obj(path, V, F):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("# procedural box humanoid, Sprite Forge gaelic-fit fixture, no photograph\n")
        for v in V:
            f.write("v %.5f %.5f %.5f\n" % (v[0], v[1], v[2]))
        for v in V:
            f.write("vt %.4f %.4f\n" % ((v[0] * 0.2) % 1.0, (v[1] * 0.2) % 1.0))
        for tri in F:
            a, b, c = int(tri[0]) + 1, int(tri[1]) + 1, int(tri[2]) + 1
            f.write("f %d/%d %d/%d %d/%d\n" % (a, a, b, b, c, c))


def _png(rgb=(196, 164, 132), size=8):
    from PIL import Image
    im = Image.new("RGB", (size, size), rgb)
    bio = io.BytesIO(); im.save(bio, format="PNG"); return bio.getvalue()


def _source_png(rig):
    tex = None
    for im in (rig.textures or {}).values():
        tex = im
        break
    if tex is None:
        return _png(), "flat"
    im = tex.convert("RGB")
    if max(im.size) > 512:
        im.thumbnail((512, 512))
    bio = io.BytesIO(); im.save(bio, format="PNG")
    return bio.getvalue(), "embedded-source"


def _parts_text(parts):
    lines = ["# mesh variant role  (gaelic-fit: body plus kit shells. Kit UVs use the squad atlas.)"]
    for i, p in enumerate(parts):
        lines.append("%d 0 %s" % (i, p.role))
    return "\n".join(lines) + "\n"


def _command_line(src, template, out, preview, smooth):
    bits = ["python3", "forge.py", "gaelic-fit", _rel(src), "--template", _rel(template), "--out", _rel(out)]
    if preview:
        bits.append("--preview")
    if smooth != 4:
        bits.extend(["--smooth", str(smooth)])
    return " ".join(shlex.quote(b) for b in bits)


def signatures_match(a, b):
    if set(a) != set(b):
        return False
    return all(a[k] == b[k] for k in a)


def write_candidate(src, template, out_dir, preview=False, smooth=4, replace=False):
    out_dir = os.path.abspath(out_dir)
    out_glb = os.path.join(out_dir, "fitted.glb")
    if _forbidden(out_dir) or _forbidden(out_glb):
        raise SystemExit(2)
    if os.path.abspath(src) == out_glb or os.path.abspath(template) == out_glb:
        raise SystemExit(2)
    if os.path.exists(out_glb) and not replace:
        print("output already exists; pass --replace to overwrite this candidate", file=sys.stderr)
        raise SystemExit(2)
    before_src = gaelic_clip._sha(src)
    before_tmpl = gaelic_clip._sha(template)
    body = load_body(template)
    rig, landmarks, notes, rec = orient_file(src)
    fitted = fit_arrays(rig.V, rig.F, body, fuv=getattr(rig, "fuv", None), landmarks=landmarks,
                        orient_notes=notes, smooth=smooth, stand=False)
    png, tex_note = _source_png(rig)
    parts, kit_report = split_kit(fitted["V"], fitted["F"], fitted["J"], fitted["W"], fitted["N"], body, fitted["UV"])
    pad = finger_pad(fitted["V"], fitted["J"], fitted["W"], body["names"], body["joints"])
    clearance, grip = grip_clearance(pad)
    os.makedirs(out_dir, exist_ok=True)
    images = {"skin": png, "kit": _png((230, 230, 230))}
    glbpack.pack_parts(template, out_glb, parts, images,
                       extras={"generator": "sprite_forge gaelic-fit", "role": "local candidate only",
                               "source": os.path.basename(src), "kit": [p["name"] for p in kit_report]})
    with open(os.path.join(out_dir, "fitted.parts"), "w", encoding="utf-8") as f:
        f.write(_parts_text(parts))
    with open(os.path.join(out_dir, "fitted.grip"), "w", encoding="utf-8") as f:
        f.write("clearance_m %.4f\n" % clearance)
    if gaelic_clip._sha(src) != before_src or gaelic_clip._sha(template) != before_tmpl:
        raise RuntimeError("an input file changed while fitting")
    joints, sig = animation_signature(out_glb)
    t_joints, t_sig = animation_signature(template)
    squad = {}
    player = _repo_player()
    if player and os.path.isfile(player) and os.path.abspath(player) != os.path.abspath(out_glb):
        p_joints, p_sig = animation_signature(player)
        squad = {"path": gaelic_clip._identity(player)["path"], "sha256": gaelic_clip._sha(player),
                 "joints_match": list(p_joints) == list(joints),
                 "channels_match": signatures_match(p_sig, sig)}
    rep = fitted["report"]
    deform = deform_report(out_glb)
    manifest = {
        "role": "local candidate only",
        "note": "Do not commit this directory and do not copy it onto assets/models/gaelic_player.glb. The game loads that file unless --model is set.",
        "command": _command_line(src, template, out_dir, preview, smooth),
        "sprite_forge": __version__,
        "source_mesh": gaelic_clip._identity(src),
        "template": gaelic_clip._identity(template),
        "output": gaelic_clip._identity(out_glb),
        "squad": squad,
        "joints": len(joints),
        "joint_order_matches_template": list(joints) == list(t_joints),
        "channels_match_template": signatures_match(sig, t_sig),
        "clips": sorted(sig),
        "required_bones_present": all(b in joints for b in gaelic_clip.REQUIRED_BONES),
        "fit": rep,
        "deform": deform,
        "texture": tex_note,
        "parts": "fitted.parts lists body then kit. The game swaps kit_*.png onto every kit mesh. Shorts UVs are in the right half; jersey, socks and boots are in the left half.",
        "kit": kit_report,
        "grip": grip,
        "kit_atlas": "Compatible. fitted.parts tags the shells as kit, and their UVs use the squad split (left jersey/socks/boots, right shorts). The body mesh keeps the source texture.",
        "gaps": GAPS,
        "provenance": "external mesh, skinned by barycentric transfer from the CC0 MakeHuman template. The source mesh's licence is not established by this file.",
        "rights": "Not established for the source mesh. A tool name in a filename is not a licence. Keep the candidate local until the mesh's author and terms are known. The template skeleton and clips are the repository's CC0 MakeHuman player.",
    }
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=1)
        f.write("\n")
    preview_path = None
    kit_diff = None
    if preview:
        preview_path = render_previews(out_glb, os.path.join(out_dir, "preview"))
        kits = render_kits(out_glb, os.path.join(out_dir, "preview"))
        if kits:
            kit_diff = kits["mean_abs_diff"]
    weights_ok = rep["unweighted"] == 0 and abs(rep["weight_sum_min"] - 1) < 0.02 and abs(rep["weight_sum_max"] - 1) < 0.02
    summary = {"ok": bool(weights_ok and manifest["channels_match_template"] and manifest["joint_order_matches_template"]),
               "out": manifest["output"]["path"] or out_glb,
               "pose": rep["pose"], "warp_arms": rep["warp_arms"], "tris": rep["tris"],
               "weight_sum": [rep["weight_sum_min"], rep["weight_sum_max"]],
               "unweighted": rep["unweighted"], "max_influences": rep["max_influences"],
               "channels_match_template": manifest["channels_match_template"], "joints": len(joints),
               "deform_flags": deform["flags"], "preview": preview_path, "kit_mean_abs_diff": kit_diff,
               "poly_warning": rep["poly_warning"], "far_fraction": rep["far_fraction"]}
    return summary


def main(argv):
    import argparse
    p = argparse.ArgumentParser(prog="forge.py gaelic-fit", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mesh", help="GLB, glTF, or OBJ. A T-pose or an A-pose, rigged or not. Not written to.")
    p.add_argument("--template", help="skeleton + body weights + clips (default: the repo MakeHuman template)")
    p.add_argument("--out", required=True, help="scratch directory for fitted.glb, fitted.parts, manifest.json")
    p.add_argument("--smooth", type=int, default=4, help="laplacian passes on the transferred weights (default 4)")
    p.add_argument("--replace", action="store_true", help="overwrite a candidate already in --out")
    p.add_argument("--preview", action="store_true", help="write preview/deform_sheet.png (software skinning, not the game)")
    a = p.parse_args(argv)
    template = a.template or _repo_template()
    if not template or not os.path.isfile(template):
        print("template GLB not found. Pass --template path/to/makehuman_template.glb", file=sys.stderr)
        return 2
    if not os.path.isfile(a.mesh):
        print("mesh not found: %s" % a.mesh, file=sys.stderr)
        return 2
    try:
        summary = write_candidate(a.mesh, template, a.out, preview=a.preview, smooth=a.smooth, replace=a.replace)
    except SystemExit as e:
        if _forbidden(a.out) or _forbidden(os.path.join(os.path.abspath(a.out), "fitted.glb")):
            print("refusing to write into assets/models or assets/textures", file=sys.stderr)
        return int(e.code) if isinstance(e.code, int) else 2
    except FitRejected as e:
        print(json.dumps({"ok": False, "errors": [str(e)], "pose": e.info}, indent=1))
        return 1
    print(json.dumps(summary, indent=1))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
