#!/usr/bin/env python3
"""Record a tutorial video of the REAL Sprite Forge Studio UI (Linux: Xvfb + ffmpeg x11grab).

  python3 tools/record_tutorial.py tools/tutorials/01_photo_to_game.json

A plan is a list of segments, each rendered to its own clip, then joined:
  {"type": "card",   "title": "...", "lines": ["..."], "secs": 5}          title / chapter card (PIL)
  {"type": "gui",    "script": [steps...]}                                  the studio driven by run_script()
                                                                          (sforge/gui.py; captions come from "cap")
  {"type": "driver", "cmd": ["python3", "tools/tutorials/x.py"], "cwd": "."} any program that drives a game on
                                                                          $DISPLAY and logs captions to $SFS_CAPLOG
  {"type": "images", "items": [[path, caption, secs], ...]}               stills with captions
  {"type": "exec",   "cmd": [...]}                                          run a helper (not recorded)
Long waits (a build) are sped up: run_script logs "@fast" / "@normal" markers around each build.
Captions are burned in with libass. Nothing here is AI-generated: it is screen capture of the real program."""
import os as _os, sys as _sys, shutil as _sh
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
try:
    from sforge.media import ffmpeg_exe as _ffx
    FFMPEG = _ffx()[0] or "ffmpeg"
except Exception:
    FFMPEG = "ffmpeg"

import json, os, subprocess, sys, time, shutil, tempfile
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H = 1400, 900
OW, OH = 1280, 822
FPS = 12
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONTB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def font(b, s):
    try:
        return ImageFont.truetype(FONTB if b else FONT, s)
    except OSError:
        return ImageFont.load_default()


def card_png(path, title, lines, sub=""):
    im = Image.new("RGB", (OW, OH), (22, 26, 38)); d = ImageDraw.Draw(im)
    d.rectangle([0, 0, OW, 8], fill=(46, 194, 126))
    d.text((70, 150), title, fill=(255, 255, 255), font=font(True, 48))
    y = 250; f = font(False, 27)
    for ln in lines:
        words = ln.split(" "); cur = ""
        for wd in words:                       # wrap to the card width
            t = (cur + " " + wd) if cur else wd
            if d.textlength(t, font=f) > OW - 150 and cur:
                d.text((76, y), cur, fill=(205, 215, 230), font=f); y += 40; cur = "   " + wd
            else:
                cur = t
        d.text((76, y), cur, fill=(205, 215, 230), font=f); y += 46
    d.text((70, OH - 70), sub or "Sprite Forge Studio - tutorial (screen recording of the real program)", fill=(120, 140, 160), font=font(False, 20))
    im.save(path)


def still_png(path, src, cap):
    im = Image.new("RGB", (OW, OH), (22, 26, 38))
    s = Image.open(src).convert("RGBA"); s.thumbnail((OW - 40, OH - 120))
    bg = Image.new("RGBA", s.size, (50, 54, 66, 255)); bg.alpha_composite(s)
    im.paste(bg.convert("RGB"), ((OW - s.width) // 2, 20 + (OH - 120 - s.height) // 2))
    im.save(path)
    return cap


def ass_header():
    return ("[Script Info]\nScriptType: v4.00+\nPlayResX: %d\nPlayResY: %d\n\n[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
            "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Cap,DejaVu Sans,26,&H00FFFFFF,&H00FFFFFF,&H20201810,&H20201810,0,0,0,0,100,100,0,0,3,10,0,2,40,40,22,1\n"
            "Style: Fast,DejaVu Sans,22,&H0000E0FF,&H00FFFFFF,&H20201810,&H20201810,1,0,0,0,100,100,0,0,3,6,0,9,20,20,20,1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n") % (OW, OH)


def ts(t):
    t = max(0.0, t); h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return "%d:%02d:%05.2f" % (h, m, s)


def burn(src, events, out, dur=None):
    """events: [(start, end, style, text)]"""
    ass = out + ".ass"
    with open(ass, "w") as f:
        f.write(ass_header())
        for a, b, st, tx in events:
            if tx and b > a:
                f.write("Dialogue: 0,%s,%s,%s,,0,0,0,,%s\n" % (ts(a), ts(b), st, tx.replace("\n", "\\N")))
    vf = "scale=%d:%d:flags=lanczos,fps=%d,ass=%s" % (OW, OH, FPS, ass)
    cmd = [FFMPEG, "-y", "-loglevel", "error", "-i", src, "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "27",
           "-pix_fmt", "yuv420p", "-r", str(FPS), "-an"]
    if dur:
        cmd += ["-t", "%.2f" % dur]
    subprocess.run(cmd + [out], check=True)


def caps_to_events(caps, t0, mapf, end):
    """caps: [(abs_time, text)] -> subtitle events in output time."""
    ev = []
    for i, (t, tx) in enumerate(caps):
        if tx.startswith("@"):
            continue
        nxt = [c for c in caps[i + 1:] if not c[1].startswith("@")]
        b = nxt[0][0] if nxt else t0 + end
        ev.append((mapf(t - t0), mapf(b - t0), "Cap", tx))
    return ev


def record(disp, raw, run):
    """Start x11grab, run run() (blocking), stop. Returns (t_start, t_end)."""
    ff = subprocess.Popen([FFMPEG, "-y", "-loglevel", "error", "-f", "x11grab", "-draw_mouse", "1", "-framerate", str(FPS),
                           "-video_size", "%dx%d" % (W, H), "-i", disp + ".0", "-c:v", "libx264", "-preset", "ultrafast",
                           "-qp", "0", raw], stdin=subprocess.PIPE)
    time.sleep(0.6); t0 = time.time()
    try:
        run()
    finally:
        time.sleep(0.5); t1 = time.time()
        ff.communicate(b"q", timeout=60)
    return t0, t1


def speed_map(caps, t0, factor):
    """Regions between @fast and @normal markers play `factor` x faster."""
    regs = []; a = None
    for t, tx in caps:
        if tx == "@fast":
            a = t - t0
        elif tx == "@normal" and a is not None:
            regs.append((a, t - t0)); a = None
    def mapf(t):
        out = t
        for ra, rb in regs:
            if t > ra:
                out -= (min(t, rb) - ra) * (1 - 1.0 / factor)
        return out
    return regs, mapf


def squeeze(raw, regs, factor, out):
    if not regs:
        shutil.copy(raw, out); return
    cond = "+".join("between(t,%.3f,%.3f)" % r for r in regs)
    sel = "select='not(%s)+(%s)*not(mod(n\\,%d))',setpts=N/(%d*TB)" % (cond, cond, factor, FPS)
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-i", raw, "-vf", sel, "-c:v", "libx264", "-preset", "ultrafast", "-qp", "0", out], check=True)


def read_caps(path):
    caps = []
    if os.path.exists(path):
        for ln in open(path):
            try:
                d = json.loads(ln); caps.append((d["t"], d["cap"]))
            except ValueError:
                pass
    return caps


def main():
    plan = json.load(open(sys.argv[1]))
    out = os.path.join(ROOT, plan["out"]); os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="sfs_vid_")
    disp = plan.get("display", ":88")
    xv = subprocess.Popen(["Xvfb", disp, "-screen", "0", "%dx%dx24" % (W, H)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.0)
    env = dict(os.environ, DISPLAY=disp)
    clips = []
    factor = plan.get("speedup", 6)
    try:
        for i, seg in enumerate(plan["segments"]):
            clip = os.path.join(tmp, "clip%02d.mp4" % i); kind = seg["type"]
            print("segment", i, kind, flush=True)
            if kind == "exec":                  # helper step, not recorded (e.g. render the FBX check)
                subprocess.run(seg["cmd"], cwd=ROOT, env=env, timeout=seg.get("timeout", 600), check=True)
                continue
            if kind == "card":
                png = os.path.join(tmp, "card%02d.png" % i)
                card_png(png, seg["title"], seg.get("lines", []), seg.get("sub", ""))
                subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-loop", "1", "-i", png, "-t", str(seg.get("secs", 5)), "-r", str(FPS),
                                "-c:v", "libx264", "-preset", "veryfast", "-crf", "27", "-pix_fmt", "yuv420p", clip], check=True)
            elif kind == "images":
                parts = []
                for j, (src, cap, secs) in enumerate(seg["items"]):
                    png = os.path.join(tmp, "img%02d_%02d.png" % (i, j)); still_png(png, src, cap)
                    c = os.path.join(tmp, "img%02d_%02d.mp4" % (i, j))
                    rawc = c + ".raw.mp4"
                    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-loop", "1", "-i", png, "-t", str(secs), "-r", str(FPS),
                                    "-c:v", "libx264", "-preset", "ultrafast", "-qp", "0", rawc], check=True)
                    burn(rawc, [(0, secs, "Cap", cap)], c, secs); parts.append(c)
                concat(parts, clip, tmp)
            elif kind in ("gui", "driver"):
                caplog = os.path.join(tmp, "caps%02d.jsonl" % i); flag = os.path.join(tmp, "flag%02d" % i)
                raw = os.path.join(tmp, "raw%02d.mkv" % i)
                def run():
                    if kind == "gui":
                        d = {"script": seg["script"], "caplog": caplog, "flag": flag}
                        g = subprocess.Popen([sys.executable, "sprite_forge_studio.py"], cwd=ROOT,
                                             env=dict(env, SFS_AUTOTEST=json.dumps(d)), stdout=open(raw + ".log", "w"), stderr=subprocess.STDOUT)
                        t = time.time()
                        while not os.path.exists(flag) and time.time() - t < seg.get("timeout", 400) and g.poll() is None:
                            time.sleep(0.2)
                        time.sleep(seg.get("tail", 1.0)); g.kill()
                    else:
                        subprocess.run(seg["cmd"], cwd=os.path.join(ROOT, seg.get("cwd", ".")), env=dict(env, SFS_CAPLOG=caplog), timeout=seg.get("timeout", 400))
                t0, t1 = record(disp, raw, run)
                caps = read_caps(caplog)
                regs, mapf = speed_map(caps, t0, factor)
                sq = os.path.join(tmp, "sq%02d.mkv" % i); squeeze(raw, regs, factor, sq)
                ev = caps_to_events(caps, t0, mapf, t1 - t0)
                ev += [(mapf(a), mapf(b), "Fast", ">> %dx speed (build running)" % factor) for a, b in regs]
                burn(sq, ev, clip)
            clips.append(clip)
        concat(clips, out, tmp)
    finally:
        xv.kill()
    try:
        from sforge.media import probe as _probe
        pr = _probe(out)
    except Exception:
        pr = {}
    print("video ->", out, "%.1f MB" % (os.path.getsize(out) / 1e6), pr)
    if not plan.get("keep_tmp"):
        shutil.rmtree(tmp, ignore_errors=True)


def concat(parts, out, tmp):
    lst = os.path.join(tmp, "list_%d.txt" % abs(hash(out)))
    with open(lst, "w") as f:
        for p in parts:
            f.write("file '%s'\n" % p)
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c:v", "libx264", "-preset", "veryfast",
                    "-crf", "27", "-pix_fmt", "yuv420p", "-r", str(FPS), "-movflags", "+faststart", out], check=True)


if __name__ == "__main__":
    main()
