#!/usr/bin/env python3
"""Arena FC v2 network integration test - reconnect, host migration, rollback.

Point it at a running v2 server (ideally started with --peer-host):

    python3 Tools/net_v2_smoketest.py --url ws://127.0.0.1:7777

It uses three simulated friends, drops the host mid-match, checks that the
room keeps running and the host role migrates, reconnects the dropped player
with its secure token into the SAME slot/team/controlled player at the live
match tick, and verifies the trailing input log + RNG word used by rollback.
Pure stdlib: reuses the dependency-free WebSocket client from net_smoketest.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from net_smoketest import WS, drain, state_hash  # noqa: E402

VER = 2
fails: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("  PASS  " if ok else "  FAIL  ") + name + (("  " + detail) if detail else ""))
    if not ok:
        fails.append(name)


def health(url: str) -> dict:
    http = "http://" + url.split("://", 1)[1].split("/")[0] + "/health"
    with urllib.request.urlopen(http, timeout=5) as r:
        return json.loads(r.read().decode())


def hello(ws: WS, name: str, room: str = "", token: str | None = None, create: bool = False) -> list[dict]:
    p = {"t": "hello", "ver": VER, "name": name, "room": room, "create": create}
    if token:
        p["token"] = token
    ws.send(p)
    return drain(ws, 0.9)


def welcome(msgs: list[dict]) -> dict | None:
    return next((m for m in msgs if m.get("t") == "welcome"), None)


def pong_all(peers: list[WS], msgs: list[dict]) -> None:
    for m in msgs:
        if m.get("t") == "ping":
            for p in peers:
                try:
                    p.send({"t": "pong", "ms": m.get("ms", 0)})
                except Exception:
                    pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="ws://127.0.0.1:7777")
    ap.add_argument("--seconds", type=float, default=2.5)
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    h0 = health(a.url)
    check("server reports protocol v2", h0.get("protocol") == VER, str(h0.get("protocol")))
    check("server exposes reconnect grace", h0.get("reconnectGraceSeconds", 0) >= 5,
          str(h0.get("reconnectGraceSeconds")))
    peer_mode = bool(h0.get("peerHost"))
    print(f"Arena FC v2 network test -> {a.url}  (peer-host mode: {peer_mode})\n")

    # ---- three friends in one room ----
    A, B, C = WS(a.url), WS(a.url), WS(a.url)
    ma = hello(A, "Ada", create=True)
    wa = welcome(ma)
    check("host receives welcome", wa is not None)
    if not wa:
        return 1
    code = wa["room"]
    token_a = wa.get("token", "")
    check("welcome issues a 256-bit resume token", len(token_a) >= 43, f"len={len(token_a)}")
    check("welcome advertises authority + grace",
          wa.get("authority") == 0 and wa.get("grace", 0) >= 5, str(wa))
    mb = hello(B, "Bo", code)
    mc = hello(C, "Cy", code)
    wb, wc = welcome(mb), welcome(mc)
    check("three players occupy slots 0/1/2",
          bool(wb and wc) and [wa["slot"], wb["slot"], wc["slot"]] == [0, 1, 2])
    token_b = wb.get("token", "") if wb else ""
    check("each player gets a distinct token", token_a != token_b and len(token_b) >= 43)

    A.send({"t": "start"})
    begins = drain(A, 0.8) + drain(B, 0.2) + drain(C, 0.2)
    check("host starts the match", any(m.get("t") == "begin" for m in begins))

    # ---- play, collecting rollback-capable snapshots on the observer ----
    snaps: list[dict] = []
    t0 = time.time()
    seq = 0
    while time.time() - t0 < a.seconds:
        seq += 1
        for sock, mv in ((A, .6), (B, -.5), (C, .2)):
            sock.send({"t": "input", "seq": seq, "cmd": {"mx": mv, "my": .1, "sp": True}})
        for sock in (A, B, C):
            try:
                pong_all([A, B, C], sock.pump(0.0))
            except Exception:
                pass
        for m in C.pump(0.0):
            if m.get("t") == "snap":
                snaps.append(m)
        time.sleep(.008)
    for m in drain(C, .5):
        if m.get("t") == "snap":
            snaps.append(m)
    check("observer received authoritative snapshots", len(snaps) > 10, f"n={len(snaps)}")
    if not snaps:
        return 1
    last = snaps[-1]
    check("snapshots carry RNG word for deterministic re-simulation", "rng" in last, str(last.get("rng")))
    check("snapshots carry global time", "gt" in last, str(last.get("gt")))
    check("snapshots carry a trailing authoritative input log",
          isinstance(last.get("inputs"), list) and len(last["inputs"]) > 0,
          f"n={len(last.get('inputs', []))}")
    check("input frames have tick + per-player commands",
          all("t" in f and "c" in f for f in last.get("inputs", [])),
          str(last.get("inputs", [])[:1])[:220])
    check("snapshots carry per-slot controlled players", len(last.get("ctrls", [])) >= 3,
          str(last.get("ctrls")))
    ctrl_before = last["ctrls"][0]
    tick_before = last["tick"]
    check("clock advanced before the drop", last.get("clock", 0) > 0, f"clock={last.get('clock')}")

    # ---- drop the host; the room must keep running ----
    A.close()
    after: list[dict] = []
    for sock in (B, C):
        after += drain(sock, 1.0)
    hosts = [m for m in after if m.get("t") == "host"]
    check("host migration is broadcast", any(m.get("host") == 1 for m in hosts),
          str([(m.get("host"), m.get("reason")) for m in hosts]))
    check("migration notice names the previous host", any(m.get("slot") == 0 for m in hosts))
    lobbies = [m for m in after if m.get("t") == "lobby"]
    check("lobby shows the disconnected slot as reserved",
          any(m.get("onlines") and False in m["onlines"] and m.get("host") == 1 for m in lobbies),
          str([m.get("onlines") for m in lobbies]))

    # ---- peer-host simulation handoff (when enabled) ----
    authority = next((m for m in after if m.get("t") == "authority"), None)
    if peer_mode:
        check("new host receives a full authoritative state handoff",
              authority is not None and authority.get("full") is not None)
        if authority and authority.get("full"):
            check("handoff contains a live tick + full roster + ball",
                  authority["full"].get("tick", 0) > 0 and
                  len(authority["full"].get("players", [])) == 10 and
                  "ball" in authority["full"],
                  f"tick={authority['full'].get('tick')}")
        # Act as the migrated peer host: submit authoritative snapshots.
        full = (authority or {}).get("full") or {}
        ptick = full.get("tick", tick_before)
        relayed: list[dict] = []
        for i in range(14):
            ptick += 3
            f = dict(full)
            f["tick"] = ptick
            B.send({
                "t": "submit", "tick": ptick, "full": f,
                "players": last.get("players", []), "ball": last.get("ball", {}),
                "score": last.get("score", [0, 0]), "clock": last.get("clock", 0),
                "phase": last.get("phase", 1), "half": last.get("half", 1),
                "ctrls": last.get("ctrls", []), "com": "peer host",
                "inputs": [{"t": ptick, "c": {"4": {"mx": .3}}}],
            })
            for sock in (B, C):
                try:
                    for m in sock.pump(0.0):
                        if m.get("t") == "snap" and sock is C:
                            relayed.append(m)
                        elif m.get("t") == "ping":
                            sock.send({"t": "pong", "ms": m.get("ms", 0)})
                except Exception:
                    pass
            time.sleep(.05)
        relayed += [m for m in drain(C, .6) if m.get("t") == "snap"]
        check("server relays peer-host submissions to other clients", len(relayed) >= 3,
              f"n={len(relayed)}")
        h = health(a.url)
        check("health counts peer submissions", h.get("submits", 0) >= 3, str(h.get("submits")))
    else:
        check("server keeps simulating after migration",
              any(m.get("t") == "snap" and m.get("tick", 0) >= tick_before for m in after))

    # ---- reconnect the dropped host with its token ----
    A2 = WS(a.url)
    mr = hello(A2, "Ada", code, token=token_a)
    wr = welcome(mr)
    resume = next((m for m in mr if m.get("t") == "resume"), None)
    check("token reconnect receives welcome", wr is not None)
    check("reconnected player keeps slot 0 and home team",
          bool(wr) and wr.get("slot") == 0 and wr.get("team") == 0, str(wr))
    check("host role stays with the migrated host", bool(wr) and wr.get("host") == 1,
          str(wr.get("host") if wr else None))
    check("welcome does not resend the bearer token", not (wr or {}).get("token"))
    check("reconnect sends a full live-match resume", resume is not None)
    if resume:
        full = resume.get("full") or {}
        check("resume checkpoint is at a live tick", full.get("tick", 0) >= tick_before,
              f"resume={full.get('tick')} before={tick_before}")
        check("resume checkpoint has the full roster + ball + RNG",
              len(full.get("players", [])) == 10 and "ball" in full and "rng" in full,
              f"players={len(full.get('players', []))}")
        check("resume keeps the same controlled player",
              resume.get("ctrls", [None])[0] == ctrl_before,
              f"{resume.get('ctrls', [None])[0]} vs {ctrl_before}")
        check("resume carries recent input frames for rollback warm-up",
              isinstance(resume.get("inputs"), list) and len(resume["inputs"]) > 0,
              f"n={len(resume.get('inputs', []))}")
        check("resume keeps the running match clock", full.get("clock", 0) > 0,
              f"clock={full.get('clock')}")
        check("resumer immediately gets a fresh snapshot",
              any(m.get("t") == "snap" for m in mr))

    # ---- an invalid token must not steal anyone's slot ----
    D = WS(a.url)
    md = hello(D, "Eve", code, token="x" * 43)
    wd = welcome(md)
    errs = [m for m in md if m.get("t") == "error"]
    check("forged token cannot reclaim a slot in a live match",
          wd is None or wd.get("slot") != 0,
          f"welcome={wd} errors={errs}")

    # ---- host can kick, and health reports the migration/reconnect ----
    B.send({"t": "kick", "kickSlot": 2})
    kickmsgs = drain(B, .5) + drain(A2, .3)
    check("migrated host exercises kick control",
          any(m.get("t") == "lobby" and 2 not in m.get("slots", [2]) for m in kickmsgs),
          str([m.get("slots") for m in kickmsgs if m.get("t") == "lobby"]))

    h1 = health(a.url)
    check("health reports at least one migration", h1.get("migrations", 0) >= 1,
          str(h1.get("migrations")))
    check("health reports at least one reconnect", h1.get("reconnects", 0) >= 1,
          str(h1.get("reconnects")))

    for s in (A2, B, C, D):
        s.close()
    print(f"\nRESULT: {'PASS' if not fails else 'FAIL'}  ({len(fails)} failures)")
    if fails:
        print("  " + "\n  ".join(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
