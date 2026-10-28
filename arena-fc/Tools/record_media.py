#!/usr/bin/env python3
"""Arena FC - deterministic gameplay video + screenshot recorder.

The clips below are NOT mockups.  Each one is produced by launching the real
exported Linux build on an Xvfb display with Godot's ``--fixed-fps`` flag,
grabbing the actual viewport of every rendered frame, and encoding those
frames into an MP4.  Keyboard/mouse input is injected with xdotool while the
frames are being generated, so the footage shows real interaction with the
running game.

Requirements (Debian/Ubuntu):
    apt-get install -y xvfb xdotool ffmpeg
    # plus a working OpenGL software rasteriser (Mesa llvmpipe) is enough.

Usage:
    python3 Tools/record_media.py --game /path/to/ArenaFC.x86_64 \
        --out /path/to/media --clip 01_match
    python3 Tools/record_media.py --game ... --out ... --clip all

The exported binary must sit next to its data_ArenaFC_linuxbsd_x86_64 folder.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# (frame number, action) -- actions fire in order once that many frames exist.
# Keys are X11 keysyms.  Held keys are released a few frames later so that
# Godot (which polls key state once per rendered frame) always sees them.
CLIPS = {
    "01_match": {
        "title": "ARENA FC - MATCH GAMEPLAY",
        "mode": "match",
        "frames": 480,          # 20 s at 24 fps
        "size": (1280, 720),
        "timeline": [
            (18,  ("down", "d")), (18,  ("down", "Shift_L")),
            (42,  ("up", "Shift_L")), (42, ("up", "d")),
            (52,  ("down", "e")),  (57,  ("up", "e")),
            (66,  ("down", "w")),  (86,  ("up", "w")),
            (96,  ("down", "q")),  (101, ("up", "q")),
            (112, ("down", "c")),  (117, ("up", "c")),
            (128, ("down", "space")), (148, ("up", "space")),
            (162, ("down", "Tab")), (167, ("up", "Tab")),
            (178, ("down", "f")),  (183, ("up", "f")),
            (194, ("down", "r")),  (199, ("up", "r")),
            (210, ("down", "e")),  (215, ("up", "e")),
            (228, ("down", "c")),  (233, ("up", "c")),
            (244, ("down", "a")),  (264, ("up", "a")),
            (276, ("down", "space")), (292, ("up", "space")),
            (304, ("down", "e")),  (309, ("up", "e")),
            (320, ("down", "Tab")), (325, ("up", "Tab")),
            (338, ("down", "Escape")), (343, ("up", "Escape")),   # pause
            (362, ("down", "Escape")), (367, ("up", "Escape")),   # resume
            (382, ("down", "c")),  (387, ("up", "c")),
            (400, ("down", "d")),  (420, ("up", "d")),
            (436, ("down", "q")),  (441, ("up", "q")),
            (452, ("down", "space")), (468, ("up", "space")),
        ],
        "shots": [(6, "01_kickoff.png"), (140, "02_charged_shot.png"),
                  (345, "03_pause_menu.png"), (440, "04_match_action.png")],
    },
    "05_cameras": {
        "title": "ARENA FC - SIX CAMERA VIEWS, ZOOM & SELECTION RING",
        "mode": "match",
        "frames": 504,          # 21 s at 24 fps
        "size": (1280, 720),
        "timeline": [
            (8,  ("down", "1")), (12, ("up", "1")),           # Broadcast
            (24, ("wheel", -1)), (28, ("wheel", -1)), (32, ("wheel", -1)),
            (70, ("down", "2")), (74, ("up", "2")),           # Telephoto
            (78, ("wheel", 1)), (82, ("wheel", 1)),
            (120, ("down", "3")), (124, ("up", "3")),         # Player cam
            (160, ("wheel", -1)), (164, ("wheel", -1)),
            (200, ("down", "4")), (204, ("up", "4")),         # Tactical
            (240, ("wheel", 1)), (244, ("wheel", 1)), (248, ("wheel", 1)),
            (280, ("down", "5")), (284, ("up", "5")),         # Behind goal
            (320, ("down", "6")), (324, ("up", "6")),         # Orbit
            (360, ("wheel", -1)), (364, ("wheel", -1)), (368, ("wheel", -1)),
            (400, ("down", "1")), (404, ("up", "1")),         # Broadcast again
            (430, ("wheel", -1)), (434, ("wheel", -1)), (438, ("wheel", -1)),
            (470, ("down", "2")), (474, ("up", "2")),         # Telephoto close finish
            (485, ("wheel", -1)), (489, ("wheel", -1)),
        ],
        "shots": [(50, "18_broadcast_close_ring.png"), (100, "19_telephoto.png"),
                  (150, "20_player_cam.png"), (220, "21_tactical.png"),
                  (300, "22_behind_goal.png"), (350, "23_orbit.png"),
                  (450, "24_zoomed_broadcast.png"), (495, "25_telephoto_close.png")],
    },
    "02_editor": {
        "title": "ARENA FC - CHARACTER / SKELETON EDITOR",
        "mode": "editor",
        "frames": 360,          # 15 s
        "size": (1280, 720),
        "timeline": [
            (24,  ("click", 160, 134)),          # select a different player
            (52,  ("drag", 1043, 102, 1170, 102)),  # taller
            (78,  ("drag", 1077, 134, 1140, 134)),  # bulkier
            (104, ("click", 855, 39)),           # Kit tab
            (136, ("click", 938, 39)),           # Face tab
            (168, ("click", 1035, 39)),          # Skeleton tab
            (196, ("click", 36, 490)),           # show bone overlay
            (222, ("drag", 1030, 214, 1140, 214)),  # rotate selected bone
            (252, ("click", 1127, 39)),          # Attributes tab
            (284, ("click", 770, 39)),           # Body tab
            (306, ("drag", 1043, 102, 900, 102)),   # shorter again
        ],
        "shots": [(20, "05_editor_body.png"), (110, "06_editor_kit.png"),
                  (180, "07_editor_skeleton.png"), (270, "08_editor_attributes.png")],
    },
    "03_menu": {
        "title": "ARENA FC - MENU, SETTINGS & KICK-OFF",
        "mode": "menu",
        "frames": 384,          # 16 s
        "size": (1280, 720),
        "timeline": [
            (40,  ("click", 225, 295)),   # MATCH SETTINGS overlay
            (92,  ("click", 640, 612)),   # Back
            (116, ("click", 225, 345)),   # CONTROLS overlay
            (168, ("click", 640, 612)),   # Back
            (196, ("click", 225, 245)),   # CHARACTER EDITOR
            (244, ("click", 831, 683)),   # Back from editor
            (272, ("click", 225, 195)),   # PLAY MATCH
        ],
        "shots": [(24, "09_main_menu.png"), (70, "10_match_settings.png"),
                  (140, "11_controls.png"), (220, "12_editor_from_menu.png"),
                  (340, "13_menu_to_match.png")],
    },
}


def run(cmd, **kw):
    return subprocess.run(cmd, **kw)


def xdo(display, *args):
    env = dict(os.environ, DISPLAY=display)
    r = run(["xdotool", *args], env=env, capture_output=True, text=True)
    return r.stdout.strip()


def frame_count(folder: Path) -> int:
    return len(list(folder.glob("f*.png")))


def perform(display: str, action):
    kind = action[0]
    if kind == "down":
        xdo(display, "keydown", "--clearmodifiers", action[1])
    elif kind == "up":
        xdo(display, "keyup", "--clearmodifiers", action[1])
    elif kind == "click":
        xdo(display, "mousemove", str(action[1]), str(action[2]), "click", "1")
    elif kind == "move":
        xdo(display, "mousemove", str(action[1]), str(action[2]))
    elif kind == "wheel":
        # X11 button 4 = wheel up (zoom in), 5 = wheel down (zoom out)
        xdo(display, "click", "4" if action[1] < 0 else "5")
    elif kind == "drag":
        _, x1, y1, x2, y2 = action
        xdo(display, "mousemove", str(x1), str(y1), "mousedown", "1")
        for i in range(1, 5):
            xdo(display, "mousemove", str(int(x1 + (x2 - x1) * i / 4)), str(int(y1 + (y2 - y1) * i / 4)))
            time.sleep(0.05)
        xdo(display, "mousemove", str(x2), str(y2), "mouseup", "1")


def record(game: Path, out: Path, name: str, cfg: dict, display_num: int, fps: int = 24):
    display = f":{display_num}"
    w, h = cfg["size"]
    frames_dir = Path("/tmp") / f"afc_record_{name}"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True)
    (out / "videos").mkdir(parents=True, exist_ok=True)
    (out / "screenshots").mkdir(parents=True, exist_ok=True)

    xvfb_log = open(f"/tmp/afc_xvfb_{name}.log", "w")
    godot_log = open(f"/tmp/afc_godot_{name}.log", "w")
    xvfb = subprocess.Popen(
        ["Xvfb", display, "-screen", "0", f"{w}x{h}x24", "-nolisten", "tcp"],
        stdout=xvfb_log, stderr=subprocess.STDOUT)
    time.sleep(1.5)

    args = [str(game), "--fixed-fps", str(fps), "--rendering-method", "gl_compatibility",
            "--rendering-driver", "opengl3", "--resolution", f"{w}x{h}", "--"]
    if cfg["mode"] == "match":
        args += ["--match"]
    elif cfg["mode"] == "editor":
        args += ["--editor"]
    args += ["--record", str(frames_dir), "--frames", str(cfg["frames"])]

    env = dict(os.environ, DISPLAY=display, LIBGL_ALWAYS_SOFTWARE="1", GALLIUM_DRIVER="llvmpipe")
    proc = subprocess.Popen(args, cwd=str(game.parent), env=env,
                            stdout=godot_log, stderr=subprocess.STDOUT)

    # Wait for the window, then set the X input focus so keys reach Godot.
    wid = ""
    for _ in range(60):
        wid = xdo(display, "search", "--name", "^Arena FC$")
        if wid:
            break
        time.sleep(0.25)
    if wid:
        xdo(display, "windowfocus", "--sync", wid.splitlines()[-1])

    timeline = sorted(cfg["timeline"], key=lambda a: a[0])
    shots = sorted(cfg["shots"], key=lambda a: a[0])
    idx = shot_idx = 0
    last = -1
    deadline = time.time() + 900
    while time.time() < deadline:
        n = frame_count(frames_dir)
        if n != last:
            last = n
            if n % 48 == 0:
                print(f"  [{name}] {n}/{cfg['frames']} frames", flush=True)
        while idx < len(timeline) and n >= timeline[idx][0]:
            perform(display, timeline[idx][1])
            idx += 1
        while shot_idx < len(shots) and n > shots[shot_idx][0]:
            src = frames_dir / f"f{shots[shot_idx][0]:05d}.png"
            if src.exists():
                shutil.copy2(src, out / "screenshots" / shots[shot_idx][1])
            shot_idx += 1
        if proc.poll() is not None:
            # fire anything remaining that was produced
            while shot_idx < len(shots):
                src = frames_dir / f"f{shots[shot_idx][0]:05d}.png"
                if src.exists():
                    shutil.copy2(src, out / "screenshots" / shots[shot_idx][1])
                shot_idx += 1
            break
        time.sleep(0.12)
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
    xvfb.terminate()
    try:
        xvfb.wait(timeout=10)
    except subprocess.TimeoutExpired:
        xvfb.kill()
    xvfb_log.close()
    godot_log.close()

    produced = frame_count(frames_dir)
    print(f"  [{name}] captured {produced} frames", flush=True)
    if produced < 20:
        print(f"  [{name}] FAILED - see /tmp/afc_godot_{name}.log", flush=True)
        return False

    # Frame 0 is the blank pre-render frame; start at 1.
    dst = out / "videos" / f"{name}.mp4"
    enc = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps),
           "-start_number", "1", "-i", str(frames_dir / "f%05d.png"),
           "-vf", f"scale={w}:{h},format=yuv420p",
           "-c:v", "libx264", "-preset", "medium", "-crf", "23",
           "-movflags", "+faststart", "-pix_fmt", "yuv420p", str(dst)]
    rc = run(enc, capture_output=True, text=True)
    if rc.returncode != 0:
        print(rc.stderr[-2000:], flush=True)
        return False
    print(f"  [{name}] {dst} ({dst.stat().st_size/1e6:.2f} MB)", flush=True)
    shutil.rmtree(frames_dir, ignore_errors=True)
    return True


def record_browser(out: Path, web_dir: Path, display_num: int, fps: int = 12, seconds: int = 20):
    """Real-time X11 capture of the exported web build running in Chromium."""
    display = f":{display_num}"
    port = 8123 + display_num % 50
    name = "04_browser"
    (out / "videos").mkdir(parents=True, exist_ok=True)
    (out / "screenshots").mkdir(parents=True, exist_ok=True)
    serve = Path(__file__).resolve().parent / "serve_web.py"

    server_log = open("/tmp/afc_browser_server.log", "w")
    xvfb_log = open("/tmp/afc_browser_xvfb.log", "w")
    chrome_log = open("/tmp/afc_browser_chromium.log", "w")
    ff_log = open("/tmp/afc_browser_ffmpeg.log", "w")
    server = subprocess.Popen([sys.executable, str(serve), "--port", str(port), "--dir", str(web_dir)],
                              stdout=server_log, stderr=subprocess.STDOUT)
    xvfb = subprocess.Popen(["Xvfb", display, "-screen", "0", "1280x720x24", "-nolisten", "tcp"],
                            stdout=xvfb_log, stderr=subprocess.STDOUT)
    time.sleep(1.5)
    env = dict(os.environ, DISPLAY=display, LIBGL_ALWAYS_SOFTWARE="1")
    profile = Path("/tmp/afc_chrome_media")
    shutil.rmtree(profile, ignore_errors=True)
    chrome = subprocess.Popen([
        "chromium", "--no-sandbox", "--test-type", "--disable-infobars",
        "--disable-dev-shm-usage", "--enable-unsafe-swiftshader",
        "--use-gl=angle", "--use-angle=swiftshader", "--window-size=1280,720",
        "--window-position=0,0", f"--app=http://127.0.0.1:{port}/index.html",
        f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
        "--disable-features=TranslateUI"], env=env, stdout=chrome_log, stderr=subprocess.STDOUT)
    print("  [04_browser] waiting ~28 s for the 39 MB WebAssembly build to boot …", flush=True)
    time.sleep(28)

    timeline = [
        (1.0, ("click", 300, 324)),                       # PLAY 5-A-SIDE
        (2.5, ("wheel", -1)), (2.9, ("wheel", -1)),       # zoom in
        (5.0, ("down", "2")), (5.5, ("up", "2")),         # Telephoto
        (8.0, ("down", "3")), (8.5, ("up", "3")),         # Player cam
        (10.5, ("wheel", 1)), (10.9, ("wheel", 1)),
        (12.5, ("down", "4")), (13.0, ("up", "4")),       # Tactical
        (15.0, ("down", "1")), (15.5, ("up", "1")),       # Broadcast
        (16.0, ("down", "d")), (17.5, ("up", "d")),
        (17.0, ("down", "space")), (18.5, ("up", "space")),
        (18.5, ("down", "e")), (19.2, ("up", "e")),
    ]
    dst = out / "videos" / f"{name}.mp4"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "x11grab", "-framerate", str(fps),
           "-video_size", "1280x720", "-i", f"{display}.0", "-t", str(seconds),
           "-vf", "format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "25",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dst)]
    ff = subprocess.Popen(cmd, env=env, stdout=ff_log, stderr=subprocess.STDOUT)
    t0 = time.time()
    idx = 0
    while ff.poll() is None and time.time() - t0 < seconds + 3:
        t = time.time() - t0
        while idx < len(timeline) and t >= timeline[idx][0]:
            perform(display, timeline[idx][1])
            idx += 1
        time.sleep(0.05)
    try:
        ff.wait(timeout=20)
    except subprocess.TimeoutExpired:
        ff.kill()
    ok = dst.exists() and dst.stat().st_size > 100_000
    if ok:
        run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "12", "-i", str(dst),
             "-frames:v", "1", str(out / "screenshots" / "14_browser_webgl.png")])
        print(f"  [04_browser] {dst} ({dst.stat().st_size/1e6:.2f} MB)", flush=True)
    else:
        print("  [04_browser] capture failed; see /tmp/afc_browser_ffmpeg.log", flush=True)
    for p in (chrome, xvfb, server):
        p.terminate()
    for p in (chrome, xvfb, server):
        try:
            p.wait(timeout=8)
        except subprocess.TimeoutExpired:
            p.kill()
    for f in (server_log, xvfb_log, chrome_log, ff_log):
        f.close()
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--game", default="/home/user/arena-fc/build/linux/ArenaFC.x86_64")
    ap.add_argument("--out", default="/home/user/arena-fc/media")
    ap.add_argument("--clip", default="all", help="clip name, 'browser', or 'all'")
    ap.add_argument("--display", type=int, default=140)
    ap.add_argument("--web-dir", default="/home/user/arena-fc/build/web")
    args = ap.parse_args()
    game = Path(args.game).resolve()
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    if args.clip == "browser":
        if not record_browser(out, Path(args.web_dir).resolve(), args.display):
            sys.exit(1)
        print("All clips recorded.", flush=True)
        return
    if not game.exists():
        sys.exit(f"Game binary not found: {game}")
    names = list(CLIPS) if args.clip == "all" else [args.clip]
    for i, n in enumerate(names):
        if n not in CLIPS:
            sys.exit(f"Unknown clip {n}; choose from {list(CLIPS)}")
        print(f"=== Recording {n}: {CLIPS[n]['title']} ===", flush=True)
        if not record(game, out, n, CLIPS[n], args.display + i * 10):
            sys.exit(1)
    print("All clips recorded.", flush=True)


if __name__ == "__main__":
    main()
