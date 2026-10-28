#!/usr/bin/env python3
"""End-to-end reconnect test with the REAL Godot C# client.

    python3 Tools/net_reconnect_e2e.py --url ws://127.0.0.1:7777

Creates a room with two stdlib WebSocket "friends", boots a headless Godot C#
client into it, starts the match, kills the Godot process mid-match (simulating
a dropped connection), then boots a SECOND Godot process with --net-reconnect.
That process must reclaim the same slot/team/player from its persisted 256-bit
token and continue receiving authoritative snapshots at the LIVE tick.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from net_smoketest import WS, drain  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(os.environ.get("ARENA_FC_CACHE", Path.home() / ".cache" / "arena-fc"))
MONO = CACHE / "mono/Godot_v4.7.2-stable_mono_linux_x86_64/Godot_v4.7.2-stable_mono_linux.x86_64"
BOOKMARK = Path.home() / ".local/share/godot/app_userdata/Arena FC/arena_fc_resume.json"
fails: list[str] = []


def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + (("  " + detail) if detail else ""))
    if not ok:
        fails.append(name)


def godot_cmd(extra: list[str]) -> list[str]:
    cmd = [str(MONO), "--headless", "--path", str(ROOT),
           "--rendering-driver", "dummy", "--audio-driver", "Dummy", "--"] + extra
    if shutil.which("xvfb-run"):
        return ["xvfb-run", "-a", "-s", "-screen 0 1280x720x24"] + cmd
    return cmd


def godot_env() -> dict:
    env = dict(os.environ)
    env["DOTNET_ROOT"] = str(CACHE / "dotnet")
    env["PATH"] = str(CACHE / "dotnet") + os.pathsep + env.get("PATH", "")
    env["LIBGL_ALWAYS_SOFTWARE"] = "1"
    return env


def spawn_godot(extra: list[str], label: str) -> tuple[subprocess.Popen, Path]:
    log = ROOT / f"build/{label}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    fh = open(log, "w")
    p = subprocess.Popen(godot_cmd(extra), cwd=ROOT, env=godot_env(),
                         stdout=fh, stderr=subprocess.STDOUT, text=True)
    return p, log


def wait_godot(p: subprocess.Popen, log: Path, timeout: float) -> str:
    try:
        p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        p.wait()
    return log.read_text(errors="replace")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="ws://127.0.0.1:7777")
    ap.add_argument("--room", default="RECONN")
    a = ap.parse_args()
    print(f"Arena FC Godot reconnect E2E -> {a.url} room {a.room}\n")

    if BOOKMARK.exists():
        BOOKMARK.unlink()

    # Two stdlib friends create the room and keep it alive across the drop.
    A = WS(a.url)
    A.send({"t": "hello", "ver": 2, "name": "Ada", "room": a.room, "create": True})
    drain(A, .6)
    B = WS(a.url)
    B.send({"t": "hello", "ver": 2, "name": "Cy", "room": a.room})
    drain(B, .6)

    # Boot the real Godot client as the third friend.
    extra = ["--net-url", a.url, "--net-room", a.room, "--net-name", "GodotBo",
             "--net-probe-seconds", "6", "--net-quit-seconds", "11"]
    p1, log1 = spawn_godot(extra, "reconnect_phase1")
    time.sleep(3.0)                       # let the C# client reach the lobby
    A.send({"t": "start"})                # start while the Godot client is live
    snaps = []
    end = time.time() + 2.2
    while time.time() < end:
        for s in (A, B):
            try:
                for m in s.pump(.1):
                    if m.get("t") == "snap":
                        snaps.append(m)
                    elif m.get("t") == "ping":
                        s.send({"t": "pong", "ms": m.get("ms", 0)})
            except Exception:
                pass
    check("authoritative match produced snapshots", len(snaps) > 5, f"n={len(snaps)}")
    tick_before = snaps[-1]["tick"] if snaps else 0
    out1 = wait_godot(p1, log1, 30)       # abrupt socket drop when the process exits
    check("Godot C# client boots and connects",
          "ARENA_FC_BOOT_OK" in out1 and "Connected · room" in out1,
          [l for l in out1.splitlines() if "ARENA_FC_NET" in l][:3].__str__())
    check("Godot client persisted a resume bookmark", BOOKMARK.exists(), str(BOOKMARK))
    bm = json.loads(BOOKMARK.read_text()) if BOOKMARK.exists() else {}
    bm = {k.lower(): v for k, v in bm.items()}
    check("bookmark holds a 256-bit token + room",
          len(bm.get("token", "")) >= 43 and bm.get("room") == a.room,
          f"slot={bm.get('slot')} team={bm.get('team')}")
    check("Godot client played the match and ran rollback prediction",
          "rb=" in out1 and "ARENA_FC_NETQUIT" in out1,
          out1.split("ARENA_FC_NETQUIT")[-1][:120].replace("\n", " "))
    time.sleep(1.0)                       # let the server notice the disconnect

    # Boot a SECOND Godot process: it must reclaim the reserved slot.
    drop_extra = ["--net-reconnect", "--net-probe-seconds", "5", "--net-quit-seconds", "8"]
    p2, log2 = spawn_godot(drop_extra, "reconnect_phase2")
    out_drop = wait_godot(p2, log2, 30)
    check("reconnect uses the persisted token", "Reconnecting to" in out_drop,
          out_drop[-220:].replace("\n", " | "))
    resumed_line = re.search(r"ARENA_FC_NETQUIT[^\n]*resumed=(\w+)", out_drop)
    check("reconnect reports resumed=True", bool(resumed_line and resumed_line.group(1) == "True"),
          resumed_line.group(0) if resumed_line else out_drop[-300:].replace("\n", " | "))
    check("resume packet delivered into the live match",
          "Reconnected into the live match" in out_drop or "resumed live match" in out_drop,
          [l for l in out_drop.splitlines() if "ARENA_FC_NET" in l][-3:].__str__())
    check("reconnected client keeps playing at a live tick",
          "ARENA_FC_NETQUIT" in out_drop and
          int(re.search(r"tick=(\d+)", out_drop.split("ARENA_FC_NETQUIT")[1]).group(1)) >= tick_before - 2,
          out_drop.split("ARENA_FC_NETQUIT")[-1][:120].replace("\n", " "))

    for s in (A, B):
        s.close()
    print(f"\nRESULT: {'PASS' if not fails else 'FAIL'}  ({len(fails)} failures)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
