"""Sprite Forge Studio v9 - batch queue.

forge.py batch queue.txt|queue.json [--workers 2] [--stop-on-error] [--dry-run]

queue.txt : one forge.py command per line (anything you would type after `forge.py`), # comments, blank lines ok
            build --mannequin --name hero --recolor team_red --variants 4
            build --spec specs/goblin.txt --preset npc_enemy
            atlas out/hero out/goblin --out out/pack
queue.json: {"workers": 2, "jobs": [{"name": "hero", "args": ["build", "--mannequin", "--name", "hero"]},
                                    {"name": "red",  "config": "projects/hero.json", "set": {"recolor": "team_red"}}]}
            "config" = a project .json saved from the Studio ("set" overrides fields).
Each job runs in its own process (a crash never stops the queue unless --stop-on-error); later jobs that
need earlier ones (atlas / recolor / export-ef / qa) wait for every job before them ("after": "all" is the default
for those commands). Writes batch_report.txt + batch_report.json next to the queue file."""
from __future__ import annotations
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPENDENT = ("atlas", "recolor", "export-ef", "qa", "package", "framedata", "summary")


def load_queue(path):
    jobs, workers = [], 1
    if path.lower().endswith(".json"):
        d = json.load(open(path))
        workers = int(d.get("workers", 1))
        for i, j in enumerate(d.get("jobs", [])):
            if "config" in j:
                cfg = json.load(open(j["config"]))
                cfg.update(j.get("set", {}))
                fd, tmp = tempfile.mkstemp(suffix=".json", prefix="sfs_batch_"); os.close(fd)
                json.dump(cfg, open(tmp, "w"))
                args = ["build", "--config", tmp] + list(j.get("args", []))
            else:
                args = list(j["args"]) if isinstance(j["args"], list) else shlex.split(j["args"], posix=os.name != "nt")
            jobs.append({"name": j.get("name") or "job%d" % (i + 1), "args": args, "after": j.get("after")})
    else:
        for ln, line in enumerate(open(path, encoding="utf-8"), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("forge.py "):
                line = line[9:]
            args = shlex.split(line, posix=True)
            nm = args[args.index("--name") + 1] if "--name" in args else "line%d" % ln
            jobs.append({"name": nm, "args": args, "after": None})
    for j in jobs:
        if j["after"] is None:
            j["after"] = "all" if j["args"] and j["args"][0] in DEPENDENT else None
    return jobs, workers


def _run(job, log_dir, env):
    t = time.time()
    lf = os.path.join(log_dir, "%s.log" % "".join(c if c.isalnum() or c in "-_" else "_" for c in job["name"]))
    with open(lf, "w", encoding="utf-8") as f:
        f.write("forge.py %s\n\n" % " ".join(shlex.quote(a) for a in job["args"])); f.flush()
        rc = subprocess.call([sys.executable, os.path.join(HERE, "forge.py")] + job["args"], stdout=f, stderr=subprocess.STDOUT,
                             cwd=os.getcwd(), env=env)
    tail = open(lf, encoding="utf-8", errors="replace").read().strip().splitlines()[-3:]
    out = ""
    for line in tail:
        if "->" in line and "Done" in line:
            out = line.split("->", 1)[1].strip()
    qa = None
    if out and os.path.isfile(os.path.join(out, "qa.json")):
        qa = json.load(open(os.path.join(out, "qa.json"))).get("score")
    return {"name": job["name"], "args": job["args"], "rc": rc, "ok": rc == 0, "seconds": round(time.time() - t, 1),
            "out": out, "qa": qa, "log": lf, "last": tail[-1] if tail else ""}


def run(path, workers=None, stop_on_error=False, dry=False, log=print, progress=None):
    jobs, w = load_queue(path)
    workers = max(1, int(workers or w))
    base = os.path.splitext(path)[0]
    log_dir = base + "_logs"
    os.makedirs(log_dir, exist_ok=True)
    log("batch: %d job(s), %d worker(s) - %s" % (len(jobs), workers, path))
    if dry:
        for j in jobs:
            log("  %-18s forge.py %s%s" % (j["name"], " ".join(j["args"]), "   (after all earlier jobs)" if j["after"] else ""))
        return {"jobs": jobs, "dry": True}
    env = dict(os.environ, SFS_BATCH="1")
    results, t0, stopped = [], time.time(), False
    i = 0
    with ThreadPoolExecutor(workers) as ex:
        while i < len(jobs) and not stopped:
            group = [jobs[i]]; i += 1
            while i < len(jobs) and not jobs[i]["after"] and len(group) < 64:   # independent jobs run together
                group.append(jobs[i]); i += 1
            for r in ex.map(lambda j: _run(j, log_dir, env), group):
                results.append(r)
                log("  [%s] %-18s %5.1fs%s  %s" % ("ok" if r["ok"] else "FAIL", r["name"], r["seconds"],
                                                    "  QA %s" % r["qa"] if r["qa"] is not None else "", r["out"] or r["last"]))
                if progress:
                    progress(len(results) / len(jobs))
                if not r["ok"] and stop_on_error:
                    stopped = True
    rep = {"queue": path, "workers": workers, "seconds": round(time.time() - t0, 1), "ok": sum(r["ok"] for r in results),
           "failed": sum(not r["ok"] for r in results), "skipped": len(jobs) - len(results), "jobs": results}
    json.dump(rep, open(base + "_report.json", "w"), indent=1)
    with open(base + "_report.txt", "w") as f:
        f.write("Sprite Forge batch %s: %d ok, %d failed, %d skipped in %.1fs (%d workers)\n" % (
            os.path.basename(path), rep["ok"], rep["failed"], rep["skipped"], rep["seconds"], workers))
        for r in results:
            f.write("%-4s %-20s %6.1fs  %s  %s\n" % ("ok" if r["ok"] else "FAIL", r["name"], r["seconds"],
                                                    ("QA %s" % r["qa"]) if r["qa"] is not None else "", r["out"] or r["log"]))
    log("batch done: %d ok, %d failed, %d skipped in %.1fs -> %s_report.txt" % (rep["ok"], rep["failed"], rep["skipped"], rep["seconds"], base))
    return rep


def main(argv):
    import argparse
    p = argparse.ArgumentParser(prog="forge.py batch", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("queue"); p.add_argument("--workers", type=int)
    p.add_argument("--stop-on-error", action="store_true"); p.add_argument("--dry-run", action="store_true")
    a = p.parse_args(argv)
    r = run(a.queue, a.workers, a.stop_on_error, a.dry_run)
    return 0 if r.get("dry") or not r["failed"] else 1
