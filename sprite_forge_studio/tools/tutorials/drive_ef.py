#!/usr/bin/env python3
"""Tutorial driver: install a fighter14 build into a COPY of Egyptian Fighter (export_ef.py) and play a short
fight on $DISPLAY using the game's own test hooks (EF_FAKEPAD_DIR fake pads, EF_TEST_HP2 for a quick KO).
usage: drive_ef.py <studio out/<name>> <game copy> <char folder name e.g. char_teal> <select index>
Logs captions to $SFS_CAPLOG."""
import json, os, subprocess, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
src, game, cname, idx = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
CAP = os.environ.get("SFS_CAPLOG")
def cap(t):
    if CAP:
        open(CAP, "a").write(json.dumps({"t": time.time(), "cap": t}) + "\n")
subprocess.run([sys.executable, os.path.join(HERE, "..", "export_ef.py"), src, os.path.join(game, "assets", cname)], check=True, stdout=subprocess.DEVNULL)
cap("tools/export_ef.py turned out/%s into the game's own strip + sprites.cfg format (assets/%s)" % (os.path.basename(src), cname))
PAD = "/tmp/efpad_video"; os.makedirs(PAD, exist_ok=True)
for i in (0, 1):
    open(os.path.join(PAD, "pad%d" % i), "w").write("mapped\n")
env = dict(os.environ, EF_FAKEPAD_DIR=PAD, EF_TEST_HP2="35")
g = subprocess.Popen(["./bin/egyptian_fighter", "--windowed"], cwd=game, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
def setpad(i, *b):
    open(os.path.join(PAD, "pad%d" % i), "w").write("mapped down=%s lx=0\n" % (",".join(b) or "none"))
def tap(i, *b, hold=0.12, after=0.3):
    setpad(i, *b); time.sleep(hold); setpad(i); time.sleep(after)
try:
    time.sleep(3.0)
    cap("Egyptian Fighter (unmodified game) - character select")
    tap(0, "RB"); tap(0, "RB")
    for b in (["DDown"] * (idx // 2)) + (["DRight"] * (idx % 2)):
        tap(0, b, after=0.35)
    tap(1, "DDown", after=0.4)
    cap("Our sheet-built fighter is in the roster"); time.sleep(2.5)
    tap(0, "A"); tap(1, "A"); time.sleep(6.5)
    cap("Each move of the sheet is a game state: walk, crouch, jump, punch, kick, specials ...")
    for b, hold in ((["DRight"], 0.8), (["DDown"], 0.7), (["DUp"], 0.12), (["X"], 0.1), (["Y"], 0.1), (["B"], 0.1), (["RT"], 0.1), (["RB"], 0.8), (["Back"], 0.12)):
        setpad(0, *b); time.sleep(hold); setpad(0); time.sleep(1.1)
    cap("... and the KO plays the victory animation")
    for _ in range(14):
        tap(0, "DRight", hold=0.25, after=0.05); tap(0, "Y", hold=0.1, after=0.5)
    time.sleep(3)
    cap("")
finally:
    g.kill()
