#!/usr/bin/env python3
"""Build media/gallery.html - an offline-first media index for Arena FC.

Why this file is careful about video playback
---------------------------------------------
1. ``preload="none"`` makes a browser show 0:00 until you press play. We use
   ``preload="metadata"`` AND bake the real duration into the page, so the
   length is always visible even when metadata cannot be fetched.
2. Arena's in-app file viewer is a sandboxed iframe with no network access, so
   sibling ``videos/*.mp4`` files cannot be streamed there. Each card therefore
   embeds a tiny low-resolution teaser as a data URI and swaps to it if the
   full-size source fails to load. Thumbnails are data URIs for the same reason.
3. Durations are parsed from the MP4 ``mvhd`` atom in pure Python, so the
   generator works even when ffprobe is not installed.

Screenshot thumbnails use ffmpeg when available; without it the original PNGs
are inlined instead. Nothing here needs network access.
"""
from __future__ import annotations

import base64
import html
import re
import shutil
import struct
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEDIA = ROOT / "media"
TMP = Path("/tmp/afc_gallery_thumbs")

VIDEOS = [
    ("01_match.mp4", "Match gameplay", "1280x720 - 24 fps",
     "5-a-side kick-off, driven with real keyboard input: sprinting, passing, through balls, "
     "charged shots, camera switching, a tackle, a pause, and a second-half attack. "
     "Frames captured from the exported C# Linux build."),
    ("02_editor.mp4", "Character & skeleton editor", "1280x720 - 24 fps",
     "Selecting a player, dragging height/bulk sliders so the 18-bone skinned mesh rebuilds "
     "live, cycling the Kit / Face / Skeleton / Attributes tabs, and posing a bone."),
    ("03_menu.mp4", "Menus, settings & kick-off", "1280x720 - 24 fps",
     "Animated 3D main menu, scrollable match settings and controls overlays, a visit to the "
     "character editor, then Play Match starting an 11v11 game."),
    ("04_browser.mp4", "Browser edition (WebGL)", "1280x720 - 12 fps",
     "The exported GDScript WebAssembly build running in Chromium with software WebGL: "
     "loading the 39 MB module, clicking Play 5-A-SIDE, then cycling camera views and zooming "
     "with the ring and touch controls visible."),
    ("05_cameras.mp4", "Six cameras, zoom & selection ring", "1280x720 - 24 fps",
     "Demonstrates the requested upgrade: 1-6 select Broadcast / Telephoto / Player cam / "
     "Tactical / Behind goal / Orbit; mouse wheel zooms in and out; the controlled player "
     "keeps a pulsing ring and floating arrow at every distance."),
    ("06_friends.mp4", "Play With Friends - real online match", "1280x720 - 12 fps",
     "Two humans in one authoritative online room (FRIEND6). Captured live from an exported "
     "Linux build connected to the Arena FC server; the HUD shows room, ping and LIVE state "
     "while both selection rings move from server snapshots."),
    ("07_online_v2.mp4", "v2 online - reconnect & rollback prediction", "960x540 - 12 fps",
     "A live authoritative room with the v2 client: the HUD shows ONLINE, the authoritative "
     "tick, ping, host slot and the rollback counter (RB corrections / replayed ticks, "
     "measured error). Captured as 96 real deterministic viewport frames."),
]

SHOTS = [
    ("01_kickoff.png", "Kick-off"),
    ("02_charged_shot.png", "Player cam + charged shot"),
    ("03_pause_menu.png", "Pause menu"),
    ("04_match_action.png", "Broadcast camera, 5v5"),
    ("05_editor_body.png", "Editor - body proportions"),
    ("06_editor_kit.png", "Editor - kit"),
    ("07_editor_skeleton.png", "Editor - skeleton pose"),
    ("08_editor_attributes.png", "Editor - attributes"),
    ("09_main_menu.png", "Main menu"),
    ("10_match_settings.png", "Match settings"),
    ("11_controls.png", "Controls / input help"),
    ("12_editor_from_menu.png", "Editor opened from menu"),
    ("13_menu_to_match.png", "11v11 kick-off"),
    ("14_browser_webgl.png", "Browser edition match"),
    ("15_rig_closeup.png", "Procedural rigged character"),
    ("16_browser_edition_godot.png", "Browser edition in Godot"),
    ("17_web_build_chromium.png", "Exported web build in Chromium"),
    ("18_broadcast_close_ring.png", "Broadcast, zoomed in + ring"),
    ("19_telephoto.png", "Telephoto camera"),
    ("20_player_cam.png", "Over-the-shoulder player cam"),
    ("21_tactical.png", "Tactical top-down view"),
    ("22_behind_goal.png", "Behind-goal camera"),
    ("23_orbit.png", "Cinematic orbit camera"),
    ("24_zoomed_broadcast.png", "Broadcast, zoomed out"),
    ("25_telephoto_close.png", "Telephoto, close zoom"),
    ("26_camera_settings.png", "Default view & zoom settings"),
    ("27_browser_online.png", "WebGL browser client in an online room"),
    ("28_online_lobby.png", "Room lobby with code & player list"),
    ("29_online_match.png", "Online 1v1 with two selection rings"),
    ("30_local_2player.png", "Local 2-player, no server needed"),
    ("31_online_v2_lobby.png", "v2 lobby - reconnect, migration & rollback"),
    ("32_online_rollback_hud.png", "Live rollback HUD (tick / ping / RB)"),
]

HAVE_FFMPEG = shutil.which("ffmpeg") is not None
TEASER_SECONDS = 6.0


def ffmpeg(*args) -> bool:
    if not HAVE_FFMPEG:
        return False
    r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *args],
                       capture_output=True, text=True)
    if r.returncode != 0:
        print("ffmpeg:", r.stderr[-500:])
        return False
    return True


def mp4_duration(path: Path) -> float:
    """Read the mvhd atom. No ffprobe / no external dependency needed.

    Handles both version 0 (32-bit) and version 1 (64-bit) timescale/duration.
    Falls back to ffprobe, then to a sane default.
    """
    try:
        data = path.read_bytes()
    except OSError:
        return 0.0

    def atoms(buf: bytes, start: int, end: int):
        off = start
        while off + 8 <= end:
            size = struct.unpack_from(">I", buf, off)[0]
            typ = buf[off + 4:off + 8]
            head = 8
            if size == 1 and off + 16 <= end:
                size = struct.unpack_from(">Q", buf, off + 8)[0]
                head = 16
            elif size == 0:
                size = end - off
            if size < head or off + size > end:
                break
            yield typ, off + head, off + size
            off += size

    for typ, body, stop in atoms(data, 0, len(data)):
        if typ != b"moov":
            continue
        for sub, p, q in atoms(data, body, stop):
            if sub != b"mvhd" or p + 4 > q:
                continue
            version = data[p]
            if version == 1 and p + 32 <= q:
                scale = struct.unpack_from(">I", data, p + 20)[0]
                dur = struct.unpack_from(">Q", data, p + 24)[0]
            elif p + 20 <= q:
                scale = struct.unpack_from(">I", data, p + 12)[0]
                dur = struct.unpack_from(">I", data, p + 16)[0]
            else:
                continue
            if scale > 0:
                return dur / scale
    if shutil.which("ffprobe"):
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", str(path)], capture_output=True, text=True)
        try:
            return float(r.stdout.strip())
        except ValueError:
            pass
    return 0.0


def clock(seconds: float) -> str:
    if seconds <= 0:
        return "?:??"
    total = int(round(seconds))
    return f"{total // 60}:{total % 60:02d}"


def thumb(src: Path, dst: Path, seek: float | None = None) -> str:
    """Return a data URI for a thumbnail; works with or without ffmpeg."""
    if HAVE_FFMPEG:
        cmd = []
        if seek is not None:
            cmd += ["-ss", f"{max(0.0, seek):.2f}"]
        cmd += ["-i", str(src), "-vf", "scale=520:-2:flags=lanczos",
                "-frames:v", "1", "-q:v", "4", str(dst)]
        if ffmpeg(*cmd) and dst.exists():
            return "data:image/jpeg;base64," + base64.b64encode(dst.read_bytes()).decode()
    if src.suffix.lower() == ".png":
        return "data:image/png;base64," + base64.b64encode(src.read_bytes()).decode()
    return ""


def teaser(src: Path, dst: Path, duration: float) -> str:
    """Short, low-res, silent MP4 embedded as a data URI for offline preview."""
    if not HAVE_FFMPEG:
        return ""
    length = max(1.0, min(TEASER_SECONDS, duration - 0.2)) if duration > 1.2 else duration
    start = max(0.0, min(duration * 0.28, max(0.0, duration - length - 0.2)))
    ok = ffmpeg(
        "-ss", f"{start:.2f}", "-i", str(src), "-t", f"{length:.2f}",
        "-an", "-vf", "scale=426:-2:flags=fast_bilinear,fps=12,format=yuv420p",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "34",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dst))
    if ok and dst.exists() and dst.stat().st_size < 1_500_000:
        print(f"  teaser {src.name}: {dst.stat().st_size/1024:.0f} KB")
        return "data:video/mp4;base64," + base64.b64encode(dst.read_bytes()).decode()
    return ""


def main():
    TMP.mkdir(parents=True, exist_ok=True)
    if not HAVE_FFMPEG:
        print("  ! ffmpeg not found - inlining original PNGs, no teaser clips")

    video_cards = []
    for fn, title, meta, desc in VIDEOS:
        src = MEDIA / "videos" / fn
        if not src.exists():
            print("missing", src)
            continue
        d = mp4_duration(src)
        label = clock(d)
        poster = thumb(src, TMP / f"{fn}.jpg", seek=min(d * .4, max(0.0, d - 1)))
        inline = teaser(src, TMP / f"{fn}.teaser.mp4", d)
        # Replace the old hard-coded "~NN s" with the measured length.
        meta_txt = f"{label} - {meta}"
        safe = html.escape(fn)
        teaser_attr = f' data-teaser="{inline}"' if inline else ""
        fallback = ("Your browser cannot play MP4. "
                    f'<a href="videos/{safe}">Download the clip</a>.')
        video_cards.append(f"""
    <article class="card video">
      <div class="frame">
        <video controls preload="metadata" playsinline poster="{poster}"{teaser_attr}>
          <source src="videos/{safe}" type="video/mp4">
          {fallback}
        </video>
        <span class="dur">{label}</span>
      </div>
      <div class="body">
        <h3>{html.escape(title)}</h3>
        <p class="meta">{html.escape(meta_txt)} &middot; {src.stat().st_size/1e6:.1f} MB</p>
        <p>{html.escape(desc)}</p>
        <p class="srclabel">Full clip: <code>videos/{safe}</code></p>
        <a class="dl" href="videos/{safe}">Open / download {safe}</a>
      </div>
    </article>""")

    shot_cards = []
    for fn, title in SHOTS:
        src = MEDIA / "screenshots" / fn
        if not src.exists():
            print("missing", src)
            continue
        img = thumb(src, TMP / f"{fn}.jpg")
        shot_cards.append(f"""
      <a class="shot" href="screenshots/{html.escape(fn)}" target="_blank">
        <img loading="lazy" src="{img}" alt="{html.escape(title)}">
        <span>{html.escape(title)}</span>
      </a>""")

    doc = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Arena FC - gameplay videos &amp; screenshots</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:#081113; color:#e6f2ef;
         font:16px/1.55 system-ui,-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; }}
  .wrap {{ max-width:1180px; margin:0 auto; padding:32px 20px 80px; }}
  header {{ border-bottom:1px solid #1c3436; padding-bottom:22px; margin-bottom:30px; }}
  h1 {{ margin:0 0 6px; font-size:clamp(30px,5vw,52px); letter-spacing:.06em;
        color:#28dc8c; text-transform:uppercase; }}
  .tag {{ color:#8fb3ac; font-size:15px; }}
  h2 {{ font-size:22px; letter-spacing:.08em; text-transform:uppercase; color:#28dc8c;
        margin:38px 0 16px; }}
  .grid {{ display:grid; gap:18px; grid-template-columns:repeat(auto-fit,minmax(420px,1fr)); }}
  .card {{ background:#0d1c1e; border:1px solid #1d3a3b; border-radius:12px;
           overflow:hidden; box-shadow:0 8px 26px #0006; }}
  .frame {{ position:relative; background:#000; }}
  .card video {{ width:100%; display:block; background:#000; aspect-ratio:16/9; }}
  .dur {{ position:absolute; right:10px; top:10px; z-index:2; pointer-events:none;
          background:#04100cd9; border:1px solid #2a6e52; color:#7dffc0;
          font:600 13px/1 ui-monospace,SFMono-Regular,Menlo,monospace;
          padding:5px 8px; border-radius:5px; letter-spacing:.04em; }}
  .body {{ padding:14px 18px 18px; }}
  h3 {{ margin:0 0 2px; font-size:19px; }}
  .meta {{ margin:0 0 8px; color:#28dc8c; font-size:13px; letter-spacing:.04em; }}
  p {{ margin:0 0 10px; color:#b9cfca; font-size:14px; }}
  .srclabel {{ font-size:12px; color:#76968f; margin:0 0 12px; }}
  code {{ color:#8ce8bd; }}
  .dl {{ display:inline-block; color:#28dc8c; text-decoration:none; font-size:14px;
         border:1px solid #276b52; padding:6px 12px; border-radius:6px; }}
  .dl:hover {{ background:#12362a; }}
  .shots {{ display:grid; gap:12px; grid-template-columns:repeat(auto-fill,minmax(240px,1fr)); }}
  .shot {{ display:block; background:#0d1c1e; border:1px solid #1d3a3b; border-radius:9px;
           overflow:hidden; text-decoration:none; color:#cfe4df; }}
  .shot img {{ width:100%; display:block; aspect-ratio:16/9; object-fit:cover; }}
  .shot span {{ display:block; padding:8px 10px; font-size:13px; }}
  .shot:hover {{ border-color:#28dc8c; }}
  .note {{ background:#0d1c1e; border-left:3px solid #28dc8c; padding:14px 18px;
           border-radius:0 8px 8px 0; color:#b9cfca; font-size:14px; margin-bottom:20px; }}
  footer {{ margin-top:36px; color:#6f918b; font-size:13px; border-top:1px solid #1c3436;
            padding-top:18px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Arena FC</h1>
    <div class="tag">Real gameplay footage and screenshots - Godot 4.7.2 / C# .NET 9 -
      procedurally rigged 3D characters - recorded 27 October 2026</div>
  </header>

  <h2>Videos</h2>
  <div class="note">
    Each card shows the <strong>real clip length</strong> in the top-right badge. If you are
    viewing this page inside Arena's sandboxed file preview, the full-size MP4s stored next
    to this file cannot be streamed (the preview has no network access). A short, silent,
    low-resolution copy of each clip is embedded directly in this page and will play inline
    instead - the label under the player changes to say <em>Preview clip</em>. For the full
    quality clip, press <strong>Open / download</strong>, or extract the ZIP and open
    <code>gallery.html</code> in a normal browser.
  </div>
  <div class="grid">{''.join(video_cards)}
  </div>

  <h2>Screenshots</h2>
  <div class="shots">{''.join(shot_cards)}
  </div>

  <h2>How this was recorded</h2>
  <div class="note">
    These are not mockups. Native clips come from the exported Linux build running on an
    Xvfb display with Mesa llvmpipe; Godot's <code>--fixed-fps 24</code> forced a
    deterministic 1/24 s timestep while <code>Tools/record_media.py</code> captured the
    actual viewport of every rendered frame to PNG and injected real keyboard/mouse input
    with <code>xdotool</code>. Those PNG sequences were encoded to H.264 MP4 with
    <code>ffmpeg</code>. The browser clip is a live X11 capture of the exported WebAssembly
    build in Chromium with SwiftShader WebGL. Clip lengths in this page are parsed from the
    MP4 <code>mvhd</code> atom at build time, so they stay correct even without ffprobe.
    <br><br>
    <strong>Honest limits:</strong> this is an original indie-scale football game, not
    FIFA/PES. Characters, kits, crowd and stadium are procedural; there are no licensed
    teams, likenesses, commentary audio, motion capture, career mode, matchmaking/accounts,
    VAR or skill-move system. Online play with friends <em>is</em> implemented (room codes,
    reconnect, host migration, rollback prediction). The web edition is a reduced GDScript
    5-a-side build because Godot 4 cannot export C# to Web. macOS and Android packages are
    unsigned and iOS needs a Mac with Xcode.
  </div>

  <footer>Original code, meshes, shaders, names and UI - MIT licensed. No FIFA/PES/eFootball
    assets, branding, likenesses, kits, audio or proprietary code were used.</footer>
</div>
<script>
(function () {{
  function swap(v, reason) {{
    if (!v.dataset.teaser || v.dataset.swapped) return;
    v.dataset.swapped = "1";
    var card = v.closest(".card");
    var src = v.querySelector("source");
    if (src) src.remove();
    v.src = v.dataset.teaser;
    v.load();
    if (card) {{
      var lab = card.querySelector(".srclabel");
      if (lab) lab.innerHTML = "Preview clip (low-res, embedded) - full clip: <strong>Open / download</strong> below";
    }}
  }}
  document.querySelectorAll("video[data-teaser]").forEach(function (v) {{
    var ready = false;
    v.addEventListener("loadedmetadata", function () {{ ready = true; }});
    v.addEventListener("error", function () {{ if (!ready) swap(v, "error"); }});
    var s = v.querySelector("source");
    if (s) s.addEventListener("error", function () {{ if (!ready) swap(v, "source-error"); }});
    // A sandboxed preview may fail silently without firing an error event.
    setTimeout(function () {{
      if (!ready && v.readyState < 1 && v.networkState !== 2) swap(v, "timeout");
    }}, 1800);
  }});
}})();
</script>
</body>
</html>
"""
    out = MEDIA / "gallery.html"
    out.write_text(doc)
    print(f"wrote {out} ({out.stat().st_size/1e6:.2f} MB)")


if __name__ == "__main__":
    main()
