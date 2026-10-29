"""v8 build cache + parallel helpers (pure Python, Windows + Linux).

Two levels:
  * whole-build manifest  out/<name>/.sfs_build.json  - key = hash(settings, input file signatures, Studio code).
    Same key and every output file still there (same size) -> the build is skipped ("up to date") in well under a second.
  * per-move frame cache  $SFS_CACHE or <user cache>/sprite_forge_studio/frames/<key>/NN.png  - key = hash(everything
    that changes the pixels of ONE move).  Changing one move re-renders only that move; a new output folder or a
    rebuild after a 3D-only change re-uses every unchanged move.
Disable with SFS_CACHE=off (or --no-cache).  Workers for per-move rendering: SFS_WORKERS (default: CPU count, 1 = serial).
"""
from __future__ import annotations
import hashlib, json, os, shutil, sys, time
from dataclasses import asdict, is_dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
FORMAT = 1
_CODE = None


def enabled():
    return os.environ.get("SFS_CACHE", "").lower() not in ("off", "0", "no", "false")


def cache_root():
    c = os.environ.get("SFS_CACHE", "")
    if c and c.lower() not in ("on", "1", "yes", "true"):
        return c
    if sys.platform.startswith("win"):
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "sprite_forge_studio")


def code_hash():
    """hash of the Studio's own code: a new version never re-uses stale frames."""
    global _CODE
    if _CODE is None:
        h = hashlib.sha1(b"sfs-cache-%d" % FORMAT)
        for d in (HERE, os.path.join(os.path.dirname(HERE), "spriteforge", "tools")):
            if not os.path.isdir(d):
                continue
            for f in sorted(os.listdir(d)):
                if f.endswith(".py"):
                    with open(os.path.join(d, f), "rb") as fh:
                        h.update(f.encode()); h.update(fh.read())
        _CODE = h.hexdigest()[:16]
    return _CODE


def file_sig(p):
    """content signature of an input file / folder (small files: sha1 of the bytes; big ones: size + mtime)."""
    if not p or not isinstance(p, str):
        return p
    if os.path.isfile(p):
        st = os.stat(p)
        if st.st_size <= 64 << 20:
            h = hashlib.sha1()
            with open(p, "rb") as f:
                for b in iter(lambda: f.read(1 << 20), b""):
                    h.update(b)
            return "f:%d:%s" % (st.st_size, h.hexdigest()[:16])
        return "F:%d:%d" % (st.st_size, int(st.st_mtime))
    if os.path.isdir(p):
        h = hashlib.sha1()
        for root, dirs, files in os.walk(p):
            dirs.sort()
            if os.path.basename(root) in ("__pycache__", "inbox"):
                continue
            for f in sorted(files):
                fp = os.path.join(root, f)
                try:
                    st = os.stat(fp)
                except OSError:
                    continue
                h.update(("%s:%d:%d;" % (os.path.relpath(fp, p), st.st_size, int(st.st_mtime))).encode())
        return "d:" + h.hexdigest()[:16]
    return p


def _plain(o):
    if is_dataclass(o) and not isinstance(o, type):
        return _plain(asdict(o))
    if isinstance(o, dict):
        return {str(k): _plain(v) for k, v in sorted(o.items(), key=lambda kv: str(kv[0])) if not str(k).startswith("_")}
    if isinstance(o, (list, tuple)):
        return [_plain(v) for v in o]
    if isinstance(o, float):
        return round(o, 6)
    if isinstance(o, (str, int, bool)) or o is None:
        return o
    return repr(type(o))


def hkey(*parts):
    return hashlib.sha1(json.dumps(_plain(list(parts)), sort_keys=True, default=str).encode()).hexdigest()[:20]


# settings that only change WHICH output files are written, never the move frames
OUTPUT_ONLY = {"glb", "fbx", "blender", "strips", "gifs", "console", "dither", "profile", "profile_vars", "kits",
               "anim_export", "max_atlas", "out_root", "display_name", "root_motion", "material_split", "material_slots",
               "fbx_writer", "view_frame_pngs",
               # v9: applied to finished frames / written next to them (sforge/v9out.py), never inside a cached move
               "talk", "faces_sheet", "maps", "framedata", "qa", "lods", "fx", "blend", "variants", "variant_seed"}
PATH_FIELDS = ("spec_path", "photo", "back", "frames_dir", "sheet", "rig", "library_dir", "regions")


def input_sigs(cfg):
    s = {}
    for f in PATH_FIELDS:
        v = getattr(cfg, f, "")
        if v and isinstance(v, str) and os.path.exists(v):
            s[f] = file_sig(v)
    for grp in ("videos", "move_sheets", "view_sources"):
        for k, v in (getattr(cfg, grp, None) or {}).items():
            s["%s.%s" % (grp, k)] = file_sig(v)
    for i, mf in enumerate(getattr(cfg, "mocap_files", []) or []):
        s["mocap%d" % i] = file_sig(mf)
    if cfg.mode == "library" or cfg.rig or cfg.outfits or cfg.props or cfg.human:
        from .library import libdir
        try:
            s["library"] = file_sig(libdir(cfg.library_dir or None))
        except Exception:
            pass
    if cfg.human:
        try:
            from . import human as HU
            s["makehuman"] = file_sig(HU.assets_dir()) if HU.have_assets() else "none"
        except Exception:
            pass
    s["env.SFS_MAKEHUMAN"] = os.environ.get("SFS_MAKEHUMAN", "")
    return s


def frame_base_key(cfg):
    """everything (but the move list and output-only switches) that can change a move's pixels"""
    d = _plain(cfg)
    for k in list(d):
        if k in OUTPUT_ONLY or k == "moves":
            d.pop(k, None)
    return hkey(code_hash(), d, input_sigs(cfg))


def build_key(cfg):
    d = _plain(cfg); d.pop("cache", None)      # --no-cache re-renders but still records the build, so the next run is 'up to date'
    return hkey(code_hash(), d, input_sigs(cfg))


# ------------------------------------------------------------------ per-move frames
def _fdir(key):
    return os.path.join(cache_root(), "frames", key[:2], key)


def get_frames(key):
    if not enabled():
        return None
    d = _fdir(key)
    meta = os.path.join(d, "meta.json")
    if not os.path.isfile(meta):
        return None
    try:
        from PIL import Image
        m = json.load(open(meta))
        ims = []
        for i in range(m["n"]):
            with Image.open(os.path.join(d, "%02d.png" % i)) as im:
                ims.append(im.convert("RGBA"))
        os.utime(meta, None)
        return ims, m.get("tag", ""), m.get("note", "")
    except Exception:
        return None


def put_frames(key, ims, tag="", note=""):
    if not enabled():
        return
    d = _fdir(key)
    tmp = d + ".tmp%d" % os.getpid()
    try:
        os.makedirs(tmp, exist_ok=True)
        for i, im in enumerate(ims):
            im.save(os.path.join(tmp, "%02d.png" % i), compress_level=1)
        json.dump({"n": len(ims), "tag": tag, "note": note, "t": time.time()}, open(os.path.join(tmp, "meta.json"), "w"))
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
        os.replace(tmp, d)
    except OSError:
        shutil.rmtree(tmp, ignore_errors=True)


def prune(max_mb=None):
    """keep the frame cache under max_mb (default SFS_CACHE_MB or 800 MB), least recently used out first."""
    max_mb = float(max_mb or os.environ.get("SFS_CACHE_MB", 800))
    root = os.path.join(cache_root(), "frames")
    if not os.path.isdir(root):
        return 0
    ent = []
    for sub in os.listdir(root):
        for k in os.listdir(os.path.join(root, sub)):
            d = os.path.join(root, sub, k)
            try:
                sz = sum(os.path.getsize(os.path.join(d, f)) for f in os.listdir(d))
                ent.append((os.path.getmtime(os.path.join(d, "meta.json")), sz, d))
            except OSError:
                continue
    total = sum(e[1] for e in ent); removed = 0
    for t, sz, d in sorted(ent):
        if total <= max_mb * 1e6:
            break
        shutil.rmtree(d, ignore_errors=True); total -= sz; removed += 1
    return removed


def clear():
    shutil.rmtree(cache_root(), ignore_errors=True)


def stats():
    root = os.path.join(cache_root(), "frames")
    n = sz = 0
    if os.path.isdir(root):
        for r, _, fs in os.walk(root):
            for f in fs:
                sz += os.path.getsize(os.path.join(r, f))
            n += 1 if "meta.json" in fs else 0
    return {"dir": cache_root(), "moves": n, "mb": round(sz / 1e6, 1), "enabled": enabled()}


# ------------------------------------------------------------------ whole-build manifest
MANIFEST = ".sfs_build.json"


def _list_outputs(out):
    files = {}
    for root, _, fs in os.walk(out):
        for f in fs:
            if f == MANIFEST:
                continue
            p = os.path.join(root, f)
            files[os.path.relpath(p, out).replace("\\", "/")] = os.path.getsize(p)
    return files


def up_to_date(out, key):
    if not enabled():
        return False
    try:
        m = json.load(open(os.path.join(out, MANIFEST)))
    except Exception:
        return False
    if m.get("key") != key:
        return False
    for rel, sz in m.get("files", {}).items():
        p = os.path.join(out, rel)
        if not os.path.isfile(p) or os.path.getsize(p) != sz:
            return False
    return True


def write_manifest(out, key, extra=None):
    try:
        d = {"key": key, "t": time.time(), "files": _list_outputs(out)}
        d.update(extra or {})
        json.dump(d, open(os.path.join(out, MANIFEST), "w"))
    except OSError:
        pass


def read_manifest(out):
    try:
        return json.load(open(os.path.join(out, MANIFEST)))
    except Exception:
        return {}


# ------------------------------------------------------------------ parallel map
def workers(n_items):
    w = os.environ.get("SFS_WORKERS", "")
    w = int(w) if w.isdigit() else (os.cpu_count() or 1)
    return max(1, min(w, n_items, 16))


def pmap(fn, items, n_workers=None, prefer_fork=True):
    """map fn over items in worker processes (fork on Linux; spawn on Windows/macOS - fn and items must pickle).
    Falls back to serial on any pool error.  Order is kept."""
    items = list(items)
    nw = n_workers or workers(len(items))
    if nw <= 1 or len(items) <= 1 or os.environ.get("SFS_IN_WORKER"):     # no nested pools
        return [fn(x) for x in items]
    import multiprocessing as mp
    from concurrent.futures import ProcessPoolExecutor
    try:
        ctx = mp.get_context("fork") if (prefer_fork and "fork" in mp.get_all_start_methods() and sys.platform != "darwin") else mp.get_context("spawn")
        with ProcessPoolExecutor(max_workers=nw, mp_context=ctx, initializer=_worker_init) as ex:
            return list(ex.map(fn, items))
    except Exception as e:                    # pickling / pool problems: never fail a build because of parallelism
        print("  (parallel rendering unavailable: %s - rendering serially)" % e)
        return [fn(x) for x in items]


def _worker_init():
    os.environ["SFS_IN_WORKER"] = "1"


def can_fork():
    import multiprocessing as mp
    return "fork" in mp.get_all_start_methods() and sys.platform not in ("darwin", "win32")


def save_pngs(jobs, old_sigs=None, level=6):
    """jobs = [(PIL image, path, key)]; skips images whose pixels match old_sigs[key] and whose file is still
    there with the recorded size; encodes the rest on a thread pool. Returns {key: [sig, size]}."""
    import concurrent.futures as _cf
    old_sigs = old_sigs or {}
    sigs = {}

    def one(job):
        im, path, key = job
        sig = hashlib.sha1(im.mode.encode() + repr(im.size).encode() + im.tobytes()).hexdigest()
        o = old_sigs.get(key)
        try:
            if o and o[0] == sig and os.path.getsize(path) == o[1]:
                return key, o
        except OSError:
            pass
        im.save(path, compress_level=level)
        return key, [sig, os.path.getsize(path)]
    if len(jobs) < 4:
        res = [one(j) for j in jobs]
    else:
        with _cf.ThreadPoolExecutor(max_workers=workers(len(jobs))) as ex:
            res = list(ex.map(one, jobs))
    for k, v in res:
        sigs[k] = v
    return sigs
