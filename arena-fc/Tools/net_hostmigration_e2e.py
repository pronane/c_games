#!/usr/bin/env python3
"""End-to-end HOST MIGRATION with the real Godot C# client as the new peer host.

    # server must be started with --peer-host
    python3 Tools/net_hostmigration_e2e.py --url ws://127.0.0.1:7777

A stdlib client (caps=1, i.e. browser-class, NOT peer-host capable) creates
the room and is slot 0. A real headless Godot C# client joins as slot 1
(caps=7) and a second stdlib observer joins as slot 2. When slot 0 drops, the
server must migrate the host role AND hand the LIVE simulation to the Godot
client, which then submits authoritative snapshots at 20 Hz. The observer must
keep receiving `snap` packets with authority=1 and advancing ticks.
"""
from __future__ import annotations
import argparse
import json
import os
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
fails: list[str] = []


def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + (("  " + detail) if detail else ""))
    if not ok:
        fails.append(name)


def health(url):
    with urllib.request.urlopen("http://" + url.split("://", 1)[1].split("/")[0] + "/health", timeout=5) as r:
        return json.loads(r.read().decode())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="ws://127.0.0.1:7777")
    ap.add_argument("--room", default="MIGR8")
    a = ap.parse_args()
    print(f"Arena FC host-migration E2E -> {a.url} room {a.room}\n")
    h = health(a.url)
    if not h.get("peerHost"):
        print("  NOTE: server was not started with --peer-host; this test needs it.")
        return 2

    # Slot 0: stdlib host that cannot run the simulation (caps=1).
    A = WS(a.url)
    A.send({"t": "hello", "ver": 2, "name": "OldHost", "room": a.room, "create": True, "caps": 1})
    drain(A, .6)
    # Slot 1: real C# client, fully capable.
    env = dict(os.environ)
    env["DOTNET_ROOT"] = str(CACHE / "dotnet")
    env["PATH"] = str(CACHE / "dotnet") + os.pathsep + env.get("PATH", "")
    cmd = [str(MONO), "--headless", "--path", str(ROOT), "--rendering-driver", "dummy",
           "--audio-driver", "Dummy", "--",
           "--net-url", a.url, "--net-room", a.room, "--net-name", "GodotHost",
           "--net-quit-seconds", "16"]
    if shutil.which("xvfb-run"):
        cmd = ["xvfb-run", "-a", "-s", "-screen 0 1280x720x24"] + cmd
    log = ROOT / "build/hostmigration_godot.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    fh = open(log, "w")
    godot = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=fh, stderr=subprocess.STDOUT, text=True)
    time.sleep(3)
    # Slot 2: stdlib observer, also browser-class.
    C = WS(a.url)
    C.send({"t": "hello", "ver": 2, "name": "Observer", "room": a.room, "caps": 1})
    drain(C, .6)
    A.send({"t": "start"})
    snaps = []
    t0 = time.time()
    while time.time() - t0 < 2.0:
        for s in (A, C):
            try:
                for m in s.pump(.1):
                    if m.get("t") == "snap":
                        snaps.append(m)
                    elif m.get("t") == "ping":
                        s.send({"t": "pong", "ms": m.get("ms", 0)})
            except Exception:
                pass
    check("match produced pre-migration snapshots", len(snaps) > 5, f"n={len(snaps)}")
    tick_before = snaps[-1]["tick"] if snaps else 0

    # Drop the host. The Godot client is the only CapPeerHost client online.
    A.close()
    after: list[dict] = []
    t1 = time.time()
    while time.time() - t1 < 1.2:
        for m in C.pump(.1):
            after.append(m)
            if m.get("t") == "ping":
                C.send({"t": "pong", "ms": m.get("ms", 0)})
    check("host role migrated to the Godot client (slot 1)",
          any(m.get("t") == "host" and m.get("host") == 1 for m in after),
          str([(m.get("host"), m.get("authority")) for m in after if m.get("t") == "host"]))
    check("migration switched the room to peer authority",
          any(m.get("t") == "host" and m.get("authority") == 1 for m in after))

    # The Godot client should now be submitting authoritative snapshots.
    relayed: list[dict] = []
    t2 = time.time()
    while time.time() - t2 < 6.0:
        for m in C.pump(.15):
            if m.get("t") == "snap":
                relayed.append(m)
            elif m.get("t") == "ping":
                C.send({"t": "pong", "ms": m.get("ms", 0)})
    check("observer keeps receiving snapshots after migration", len(relayed) >= 5,
          f"n={len(relayed)}")
    check("relayed snapshots come from the peer authority",
          any(m.get("authority") == 1 for m in relayed),
          str(sorted({m.get("authority") for m in relayed})))
    check("peer-host ticks advance past the pre-drop tick",
          bool(relayed) and max(m.get("tick", 0) for m in relayed) > tick_before,
          f"before={tick_before} after={max((m.get('tick', 0) for m in relayed), default=0)}")
    h2 = health(a.url)
    check("server counted peer submissions", h2.get("submits", 0) >= 5, str(h2.get("submits")))

    try:
        godot.wait(timeout=20)
    except subprocess.TimeoutExpired:
        godot.kill(); godot.wait()
    fh.close()
    out = log.read_text(errors="replace")
    check("Godot client accepted the authoritative handoff",
          "HOST MIGRATION" in out or "authoritative simulation" in out,
          [l for l in out.splitlines() if "ARENA_FC_NET" in l][-4:].__str__())
    check("Godot client resumed rollback prediction after handoff",
          "ARENA_FC_NETQUIT" in out and "rb=" in out,
          out.split("ARENA_FC_NETQUIT")[-1][:120].replace("\n", " "))
    C.close()
    print(f"\nRESULT: {'PASS' if not fails else 'FAIL'}  ({len(fails)} failures)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
