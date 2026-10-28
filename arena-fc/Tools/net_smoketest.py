#!/usr/bin/env python3
"""Arena FC online smoke test - dependency-free WebSocket client (stdlib only).

Starts nothing itself; point it at a running server:

    python3 Tools/net_smoketest.py --url ws://127.0.0.1:7777 --seconds 6

It creates a room with two simulated friends, starts a match, streams input
for a few seconds from both, and asserts that both receive identical
authoritative snapshots (same tick, same state hash). Also checks /health.
Protocol v2 (reconnect / host migration / rollback) is covered in more depth
by net_v2_smoketest.py and net_reconnect_e2e.py.
"""
from __future__ import annotations
import argparse
import base64
import json
import os
import socket
import struct
import sys
import time
import urllib.request
from urllib.parse import urlparse


class WS:
    """Minimal RFC6455 client. Buffered, non-blocking reads: a partial frame is
    never consumed, which matters when snapshots arrive 20 times a second."""

    def __init__(self, url: str, timeout: float = 5.0):
        u = urlparse(url)
        self.host = u.hostname or "127.0.0.1"
        self.port = u.port or 7777
        self.path = (u.path or "/") + (("?" + u.query) if u.query else "")
        self.sock = socket.create_connection((self.host, self.port), timeout=timeout)
        self.sock.settimeout(timeout)
        self.buf = bytearray()
        key = base64.b64encode(os.urandom(16)).decode()
        req = (
            f"GET {self.path} HTTP/1.1\r\nHost: {self.host}:{self.port}\r\n"
            "Upgrade: websocket\r\nConnection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n"
            "Sec-WebSocket-Protocol: arenafc\r\n\r\n"
        )
        self.sock.sendall(req.encode())
        while b"\r\n\r\n" not in self.buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise RuntimeError("handshake closed")
            self.buf += chunk
        head, rest = bytes(self.buf).split(b"\r\n\r\n", 1)
        self.buf = bytearray(rest)
        if b"101" not in head.split(b"\r\n", 1)[0]:
            raise RuntimeError("handshake failed: " + head.decode(errors="replace"))
        self.sock.setblocking(False)

    def send(self, obj) -> None:
        data = (json.dumps(obj, separators=(",", ":")) if not isinstance(obj, str) else obj).encode()
        n = len(data)
        if n < 126:
            hdr = bytes([0x81, 0x80 | n])
        elif n <= 65535:
            hdr = bytes([0x81, 0x80 | 126]) + struct.pack(">H", n)
        else:
            hdr = bytes([0x81, 0x80 | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        self.sock.sendall(hdr + mask + masked)

    def pump(self, timeout: float = 0.0) -> list[dict]:
        """Read whatever is available, then parse every complete frame."""
        import select
        if timeout > 0:
            r, _, _ = select.select([self.sock], [], [], timeout)
            if not r:
                return []
        while True:
            try:
                chunk = self.sock.recv(65536)
            except (BlockingIOError, InterruptedError):
                break
            except socket.timeout:
                break
            if not chunk:
                raise RuntimeError("socket closed")
            self.buf += chunk

        out = []
        while True:
            b = self.buf
            if len(b) < 2:
                break
            b0, b1 = b[0], b[1]
            opcode = b0 & 0x0F
            n = b1 & 0x7F
            off = 2
            if n == 126:
                if len(b) < 4:
                    break
                n = struct.unpack(">H", b[2:4])[0]
                off = 4
            elif n == 127:
                if len(b) < 10:
                    break
                n = struct.unpack(">Q", b[2:10])[0]
                off = 10
            mask_len = 4 if (b1 & 0x80) else 0
            if n > 8 * 1024 * 1024 or len(b) < off + mask_len + n:
                break
            payload = bytes(b[off + mask_len: off + mask_len + n])
            if mask_len:
                mask = bytes(b[off: off + 4])
                payload = bytes(c ^ mask[i % 4] for i, c in enumerate(payload))
            del b[: off + mask_len + n]
            if opcode == 0x8:
                raise RuntimeError("server closed")
            if opcode == 0x9:      # ping -> pong
                self.send({"t": "pong"})
            elif opcode in (0x1, 0x2):
                try:
                    out.append(json.loads(payload.decode()))
                except Exception:
                    pass
        return out

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


def state_hash(snap: dict) -> str:
    bits = [snap.get("ball", {}).get("x"), snap.get("ball", {}).get("z")]
    for p in snap.get("players", []):
        bits += [p.get("x"), p.get("z")]
    return "|".join(f"{v:.2f}" if isinstance(v, (int, float)) else str(v) for v in bits)


def drain(ws: WS, seconds: float = 1.0) -> list[dict]:
    end = time.time() + seconds
    out = []
    while time.time() < end:
        out += ws.pump(0.15)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="ws://127.0.0.1:7777")
    ap.add_argument("--seconds", type=float, default=6.0)
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    failures = []

    def check(name, ok, detail=""):
        print(("  PASS  " if ok else "  FAIL  ") + name + (("  " + detail) if detail else ""))
        if not ok:
            failures.append(name)

    print(f"Arena FC online smoke test -> {a.url}\n")
    # --- HTTP health endpoint ---
    try:
        http = "http://" + a.url.split("://", 1)[1].split("/")[0] + "/health"
        with urllib.request.urlopen(http, timeout=5) as r:
            health = json.loads(r.read().decode())
        check("GET /health returns ok", health.get("ok") is True, f"rooms={health.get('rooms')}")
    except Exception as ex:
        check("GET /health returns ok", False, str(ex))

    A = WS(a.url)
    msgsA = drain(A, 0.4)
    A.send({"t": "hello", "ver": 2, "name": "Ada", "room": "", "caps": 7})
    msgsA += drain(A, 0.8)
    welcomeA = next((m for m in msgsA if m.get("t") == "welcome"), None)
    check("client A receives welcome", welcomeA is not None)
    if not welcomeA:
        print(msgsA)
        return 1
    code = welcomeA["room"]
    check("server issued a 6-char room code", len(code) == 6, code)
    check("A is host slot 0, home team", welcomeA["slot"] == 0 and welcomeA["team"] == 0,
          f"slot={welcomeA['slot']} team={welcomeA['team']}")

    B = WS(a.url)
    B.send({"t": "hello", "ver": 2, "name": "Bo", "room": code, "caps": 7})
    msgsB = drain(B, 0.8)
    welcomeB = next((m for m in msgsB if m.get("t") == "welcome"), None)
    check("client B joins the same room", welcomeB is not None and welcomeB.get("room") == code)
    check("B is slot 1, away team", bool(welcomeB and welcomeB["slot"] == 1 and welcomeB["team"] == 1),
          f"{welcomeB}")

    lobbies = [m for m in msgsA + msgsB + drain(A, 0.3) if m.get("t") == "lobby"]
    check("lobby broadcast lists both players", any(len(m.get("names", [])) == 2 for m in lobbies),
          str([m.get("names") for m in lobbies]))

    A.send({"t": "start"})
    begin = [m for m in drain(A, 1.0) + drain(B, 0.3) if m.get("t") == "begin"]
    check("host can start the match", len(begin) >= 1, f"begin packets={len(begin)}")

    # --- stream input from both humans, collect snapshots ---
    snapA, snapB = [], []
    t0 = time.time()
    seq = 0
    while time.time() - t0 < a.seconds:
        seq += 1
        A.send({"t": "input", "seq": seq, "cmd": {"mx": 0.6, "my": 0.0, "sp": True}})
        B.send({"t": "input", "seq": seq, "cmd": {"mx": -0.5, "my": 0.2}})
        if seq % 400 == 0:
            A.send({"t": "input", "seq": seq, "cmd": {"pa": True}})
        for m in A.pump(0.0):
            if m.get("t") == "snap":
                snapA.append(m)
            elif m.get("t") == "ping":
                A.send({"t": "pong", "ms": m.get("ms", 0)})
        for m in B.pump(0.0):
            if m.get("t") == "snap":
                snapB.append(m)
            elif m.get("t") == "ping":
                B.send({"t": "pong", "ms": m.get("ms", 0)})
        time.sleep(0.008)
    snapA += [m for m in drain(A, 0.6) if m.get("t") == "snap"]
    snapB += [m for m in drain(B, 0.6) if m.get("t") == "snap"]

    check("both clients receive snapshots", len(snapA) > 5 and len(snapB) > 5,
          f"A={len(snapA)} B={len(snapB)}")
    check("snapshots advance the tick", bool(snapA) and snapA[-1]["tick"] > snapA[0]["tick"],
          f"{snapA[0]['tick'] if snapA else '-'} -> {snapA[-1]['tick'] if snapA else '-'}")
    if snapA and snapB:
        common = set(m["tick"] for m in snapA) & set(m["tick"] for m in snapB)
        check("both players see the same authoritative ticks", len(common) > 3, f"shared={len(common)}")
        byTick = {m["tick"]: m for m in snapB}
        same = all(state_hash(m) == state_hash(byTick[m["tick"]]) for m in snapA if m["tick"] in byTick)
        check("shared ticks have identical world state", same)
        players = len(snapA[-1].get("players", []))
        check("snapshot contains full team state", players == 2 * snapA[-1].get("size", 5) or players >= 10,
              f"players={players}")
        check("per-slot controlled indices present", len(snapA[-1].get("ctrls", [])) >= 2,
              str(snapA[-1].get("ctrls")))
        if a.verbose:
            print("  last snapshot tick", snapA[-1]["tick"], "clock", snapA[-1].get("clock"),
                  "score", snapA[-1].get("score"), "ball", snapA[-1].get("ball"))

    # --- chat + error handling ---
    A.send({"t": "chat", "m": "gg"})
    chatB = [m for m in drain(B, 0.5) if m.get("t") == "chat"]
    check("chat is relayed to the other player", any(m.get("m") == "gg" for m in chatB))

    A.close()
    B.close()
    print(f"\nRESULT: {'PASS' if not failures else 'FAIL'}  ({len(failures)} failures)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
