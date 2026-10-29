"""Sprite Forge Studio v9 - extra outputs written after the normal build outputs:
faces.png (expression / mouth-shape portraits), talk/ (dialogue mouth strip), regions_preview.png,
maps/ (normal + emissive), framedata.json/.cfg, qa_report, LODs.  Every step is optional and isolated:
a failure becomes a build warning, never a failed build."""
import json
import os
import time

from PIL import Image

from . import expressions as X


def _png(im, path):
    im.save(path, compress_level=6)


def write_faces(cfg, out, report):
    close = getattr(cfg, "_face_close", None)
    if close is None or not cfg.faces_sheet:
        return None
    est = getattr(cfg, "_face_estimated", False)
    names = X.EXPRESSIONS + ["mouth_" + v for v in X.VISEMES if v != "rest"]
    ims = [close(n) for n in names]
    title = "%s - expressions + mouth shapes%s" % (cfg.name, " (ESTIMATED: procedural warps of the photo's own face)" if est else "")
    sheet = X.faces_sheet(ims, [n.replace("mouth_", "mouth ") for n in names], title, thumb=128, cols=7)
    _png(sheet, os.path.join(out, "faces.png"))
    os.makedirs(os.path.join(out, "faces"), exist_ok=True)
    for n, im in zip(names, ims):
        _png(im, os.path.join(out, "faces", n + ".png"))
    return "faces.png (%d portraits)" % len(names)


def write_talk(cfg, out, report):
    render = getattr(cfg, "_face_render", None)
    if render is None or not cfg.talk:
        return None
    td = os.path.join(out, "talk")
    os.makedirs(td, exist_ok=True)
    shapes = {}
    base = cfg.expr_map and X.parse_map(cfg.expr_map).get("talk") or "neutral"
    for v in X.VISEMES:
        im = render(("%s+mouth_%s" % (base, v)) if base != "neutral" else "mouth_" + v)
        shapes[v] = im
        _png(im, os.path.join(td, "mouth_%s.png" % v))
    fps = 12
    if cfg.talk.strip().lower() == "sheet":
        seq = [(v, 1) for v in X.VISEMES]
        line = ""
    else:
        line = cfg.talk
        seq = X.text_to_visemes(line, fps)
    frames = [v for v, n in seq for _ in range(n)]
    W, H = cfg.frame_w, cfg.frame_h
    cap = max(1, min(len(frames), 4096 // W))
    strip = Image.new("RGBA", (W * cap, H), (0, 0, 0, 0))
    for i, v in enumerate(frames[:cap]):
        strip.paste(shapes[v], (i * W, 0))
    _png(strip, os.path.join(td, "talk_strip.png"))
    info = {"line": line, "fps": fps, "base_expression": base, "frame_w": W, "frame_h": H,
            "shapes": {v: "mouth_%s.png" % v for v in X.VISEMES},
            "sequence": [{"shape": v, "frames": n} for v, n in seq], "frames": frames,
            "strip": "talk_strip.png", "strip_frames": cap,
            "method": "letter-based mouth shapes (not speech recognition); swap the mouth frames in time with your own audio",
            "estimated": bool(getattr(cfg, "_face_estimated", False))}
    with open(os.path.join(td, "talk.json"), "w") as f:
        json.dump(info, f, indent=1)
    return "talk/ (%d mouth shapes, %d-frame line)" % (len(X.VISEMES), len(frames))


def post_outputs(cfg, out, ctx, report):
    """ctx: dict(ordered, placed, page_names, frames, sp, spec_by, pages) -> list of output notes"""
    notes = []
    steps = [("faces", lambda: write_faces(cfg, out, report)),
             ("talk", lambda: write_talk(cfg, out, report))]
    if getattr(cfg, "variants", 0) > 0:
        def _var():
            from . import variants as VA
            vd = os.path.join(out, "variants")
            if getattr(cfg, "_base_spec", None) is not None:
                VA.write(vd, cfg._base_spec, cfg.variants, cfg.variant_seed, cfg.vary, log=report.log)
            elif getattr(cfg, "_cut_lms", None) is not None:
                VA.write_photo(vd, cfg._cut_lms[0], cfg._cut_lms[1], cfg.variants, cfg.variant_seed, cfg.vary, log=report.log)
            else:
                return None
            return "variants/ (%d, seeds %d..%d)" % (cfg.variants, cfg.variant_seed, cfg.variant_seed + cfg.variants - 1)
        steps.append(("variants", _var))
    try:
        from . import recolor as RC
        steps.append(("regions", lambda: RC.write_preview(cfg, out, ctx, report)))
    except ImportError:
        pass
    for mod, fn_name, flag in (("maps", "write_maps", "maps"), ("framedata", "write_framedata", "framedata"),
                               ("qa", "write_qa", "qa"), ("lod", "write_lods", "lods")):
        if getattr(cfg, flag, None):
            def _f(mod=mod, fn_name=fn_name):
                m = __import__("sforge." + mod, fromlist=[fn_name])
                return getattr(m, fn_name)(cfg, out, ctx, report)
            steps.append((mod, _f))
    for name, fn in steps:
        t0 = time.time()
        try:
            r = fn()
        except Exception as e:
            import traceback
            report.warning("%s: %s" % (name, e))
            if os.environ.get("SFS_DEBUG"):
                traceback.print_exc()
            continue
        if r:
            report.timing(name, time.time() - t0)
            notes.append(r)
    return notes
