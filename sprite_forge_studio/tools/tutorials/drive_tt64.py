#!/usr/bin/env python3
"""Tutorial driver: install a kart_racer build into a COPY of TurboTumble64 and drive the real game with xdotool.
usage: drive_tt64.py <studio out/<name> folder> <TurboTumble64 folder (a copy)> <grid moves e.g. Down,Down,Right>
Logs captions to $SFS_CAPLOG (used by record_tutorial.py)."""
import json, os, shutil, subprocess, sys, time
src, game, moves = sys.argv[1], sys.argv[2], sys.argv[3].split(",")
CAP = os.environ.get("SFS_CAPLOG")
def cap(t):
    if CAP:
        open(CAP, "a").write(json.dumps({"t": time.time(), "cap": t}) + "\n")
name = os.path.basename(src.rstrip("/"))
dst = os.path.join(game, "assets", "characters", name)
shutil.rmtree(dst, ignore_errors=True); shutil.copytree(src, dst)
cap("Installed: copied out/%s into TurboTumble64/assets/characters/%s - the game auto-loads any folder with a character.ini" % (name, name))
g = subprocess.Popen(["./tt64_linux"], cwd=game, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(4.5)
def key(k, after=0.7):
    subprocess.run(["xdotool", "keydown", k]); time.sleep(0.12); subprocess.run(["xdotool", "keyup", k]); time.sleep(after)
try:
    cap("TurboTumble64 (unmodified game binary) starting")
    time.sleep(1.5); key("Return", 1.2)
    cap("Time Trial -> character select")
    key("Down", 0.8); key("Return", 1.5)
    for m in moves:
        key(m, 0.6)
    cap("Our racer is in the select grid. The 3D select stage spins the kart: front, side and back sprite angles are used")
    time.sleep(7)
    key("Return", 1.5)
    cap("Pick a track and race")
    key("Return", 5.5)
    cap("Racing: the chase camera shows the BACK view (from the back photo - here a SYNTHETIC mannequin render)")
    subprocess.run(["xdotool", "keydown", "w"]); time.sleep(5)
    cap("Steering turns the kart, so the game switches to the angled / side views")
    subprocess.run(["xdotool", "keydown", "a"]); time.sleep(1.2); subprocess.run(["xdotool", "keyup", "a"]); time.sleep(1.5)
    subprocess.run(["xdotool", "keydown", "d"]); time.sleep(1.5); subprocess.run(["xdotool", "keyup", "d"]); time.sleep(3)
    subprocess.run(["xdotool", "keyup", "w"])
    cap("")
finally:
    g.kill()
