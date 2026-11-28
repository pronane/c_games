#!/usr/bin/env python3
"""Check a recorded match against Tools/recording_targets.json.

    python3 Tools/check_recording.py --video match.mp4 --report gameplay.json \
        [--log godot.log] [--targets Tools/recording_targets.json] [--out DIR] [--summary FILE]

The recording is made by the game itself (Godot --write-movie, --ai-vs-ai, --gameplay-report),
so this checks two things:

* the video is a good recording: right size and frame rate, long enough, no blank frames, no
  frozen stretches, the picture keeps changing, and the pitch is in shot;
* the match in it hits the targets: football happened (passes, possession changes, the ball and
  players moving), the players animated (clips, footsteps, planted-foot slide, lock coverage,
  contact timing), frames stayed within budget, and the game log has no C# exceptions.

It writes a contact sheet and a short GIF preview to --out, a Markdown table to --summary (the
GitHub job summary), and exits 1 if any check fails.  Only ffmpeg / ffprobe and the Python
standard library are needed.
"""
import argparse
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def probe(video):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
                          "-show_entries", "stream=width,height,r_frame_rate,nb_read_frames:format=duration",
                          "-of", "json", video], capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    st = d["streams"][0]
    num, den = st["r_frame_rate"].split("/")
    return dict(width=int(st["width"]), height=int(st["height"]), fps=float(num) / float(den or 1),
                frames=int(st.get("nb_read_frames") or 0), duration=float(d["format"]["duration"]))


def sample_frames(video, fps=2, w=96, h=54):
    """-> list of RGB frames (bytes, w*h*3) sampled at `fps`."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-vf", "fps=%g,scale=%d:%d" % (fps, w, h),
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    n = w * h * 3
    return [raw[i:i + n] for i in range(0, len(raw) - n + 1, n)]


def frame_stats(rgb):
    px = len(rgb) // 3
    lum = [0.299 * rgb[3 * i] + 0.587 * rgb[3 * i + 1] + 0.114 * rgb[3 * i + 2] for i in range(px)]
    mean = sum(lum) / px
    std = (sum((x - mean) ** 2 for x in lum) / px) ** .5
    green = sum(1 for i in range(px) if rgb[3 * i + 1] > rgb[3 * i] + 12 and rgb[3 * i + 1] > rgb[3 * i + 2] + 12) / px
    return mean, std, green


def mean_abs_diff(a, b):
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--video", required=True)
    ap.add_argument("--report", required=True, help="gameplay.json written by --gameplay-report")
    ap.add_argument("--log", help="the game's stdout/stderr, checked for C# exceptions")
    ap.add_argument("--targets", default=os.path.join(HERE, "recording_targets.json"))
    ap.add_argument("--out", default=".")
    ap.add_argument("--summary", help="append a Markdown table here (e.g. $GITHUB_STEP_SUMMARY)")
    ap.add_argument("--artifact-url", default="", help="link to the uploaded recording, for the summary")
    a = ap.parse_args(argv)
    T = json.load(open(a.targets))
    rep = json.load(open(a.report))
    os.makedirs(a.out, exist_ok=True)
    rows = []

    def check(group, name, value, ok, target):
        rows.append((group, name, value, target, ok))

    # ---- the video itself
    v = probe(a.video)
    tv = T["video"]
    check("video", "resolution", "%dx%d" % (v["width"], v["height"]),
          v["width"] == tv["width"] and v["height"] == tv["height"], "%dx%d" % (tv["width"], tv["height"]))
    check("video", "frame rate", "%.2f fps" % v["fps"], abs(v["fps"] - tv["fps"]) < .01, "%d fps" % tv["fps"])
    check("video", "duration", "%.1f s (%d frames)" % (v["duration"], v["frames"]),
          v["duration"] >= tv["min_duration_s"], ">= %.1f s" % tv["min_duration_s"])
    frames = sample_frames(a.video)
    stats = [frame_stats(f) for f in frames]
    blank = sum(1 for m, s, g in stats if s < 6 or m < 8 or m > 247)
    check("video", "blank frames", "%d of %d sampled" % (blank, len(frames)), blank <= tv["max_blank_frames"],
          "<= %d" % tv["max_blank_frames"])
    diffs = [mean_abs_diff(frames[i - 1], frames[i]) for i in range(1, len(frames))]
    run = longest = 0
    for d in diffs:
        run = run + 1 if d < .6 else 0
        longest = max(longest, run)
    frozen_s = longest / 2.0
    check("video", "longest frozen stretch", "%.1f s" % frozen_s, frozen_s <= tv["max_frozen_run_s"],
          "<= %.1f s" % tv["max_frozen_run_s"])
    moving = sum(1 for d in diffs if d >= 1.0) / max(1, len(diffs))
    check("video", "frames that change", "%.0f%%" % (moving * 100), moving >= tv["min_moving_fraction"],
          ">= %.0f%%" % (tv["min_moving_fraction"] * 100))
    pitch = sorted(g for _, _, g in stats)[len(stats) // 2] if stats else 0
    check("video", "pitch in shot (median)", "%.0f%% of the picture" % (pitch * 100), pitch >= tv["min_pitch_fraction"],
          ">= %.0f%%" % (tv["min_pitch_fraction"] * 100))

    # ---- what happened in the match
    def lim(group, key, label, fmt="%s"):
        mn, mx = T[group].get("min_" + key), T[group].get("max_" + key)
        val = rep.get(key)
        if val is None:
            check(group, label, "missing", False, "present")
            return
        ok = (mn is None or val >= mn) and (mx is None or val <= mx)
        target = (">= %s" % mn) if mn is not None else ("<= %s" % mx)
        check(group, label, fmt % val, ok, target)

    lim("gameplay", "passes", "passes")
    lim("gameplay", "possession_changes", "possession changes")
    lim("gameplay", "ball_distance_m", "ball travelled (m)")
    lim("gameplay", "player_distance_m", "players ran (m, all)")
    lim("gameplay", "distinct_clips", "animation clips used")
    lim("gameplay", "footsteps", "footsteps")
    lim("animation", "planted_foot_slide_mps", "planted-foot slide (m/s)")
    lim("animation", "planted_foot_slide_samples", "planted-foot samples")
    lim("animation", "plant_window_lock_coverage", "foot-lock coverage of plant windows")
    lim("animation", "avg_contact_frame_error", "ball-contact timing error (frames)")
    lim("performance", "sim_step_ms_p95", "simulation step p95 (ms)")
    lim("performance", "rig_sync_ms_p95", "rig sync p95 (ms, 22 rigs)")
    if a.log and os.path.exists(a.log):
        log = open(a.log, errors="replace").read()
        exc = re.findall(r"(Unhandled exception|System\.\w+Exception[^\n]*)", log)
        check("log", "C# exceptions in the game log", str(len(exc)), not exc, "0")

    # ---- previews
    sheet = os.path.join(a.out, "contact-sheet.png")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.video, "-vf",
                    "fps=%g,scale=320:-1,tile=4x3" % (12.0 / max(1.0, v["duration"])), "-frames:v", "1", sheet], check=False)
    gif = os.path.join(a.out, "preview.gif")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-t", "8", "-i", a.video, "-vf",
                    "fps=10,scale=480:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=96[p];[s1][p]paletteuse",
                    gif], check=False)

    failed = [r for r in rows if not r[4]]
    lines = ["## Gameplay recording: %s" % ("all targets met" if not failed else "%d target(s) missed" % len(failed)), ""]
    if a.artifact_url:
        lines += ["Recording, contact sheet and preview: [download](%s)" % a.artifact_url, ""]
    lines += ["Score %s-%s, %s shots, %s passes in %s s of play (%s game seconds)." % (
        rep["score"][0], rep["score"][1], rep.get("shots"), rep.get("passes"), rep.get("seconds"), rep.get("game_clock_seconds")), "",
        "| | check | value | target |", "|---|---|---|---|"]
    for group, name, value, target, ok in rows:
        lines.append("| %s | %s: %s | %s | %s |" % ("✅" if ok else "❌", group, name, value, target))
    text = "\n".join(lines) + "\n"
    print(text)
    open(os.path.join(a.out, "recording-check.md"), "w").write(text)
    json.dump(dict(passed=not failed, video=v, report=rep, checks=[dict(group=g, check=n, value=val, target=t, ok=o)
                                                                     for g, n, val, t, o in rows]),
              open(os.path.join(a.out, "recording-check.json"), "w"), indent=1)
    if a.summary:
        with open(a.summary, "a") as f:
            f.write(text)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
