#!/usr/bin/env python3
"""Compare Arena FC benchmark runs (Tests/Benchmarks) for a change against its base.

    python3 Tools/compare_benchmarks.py --base-perf b1.json [b2.json ...] --head-perf h1.json [h2.json ...] \
        --base-gameplay base_gameplay.json --head-gameplay head_gameplay.json \
        [--targets Tools/benchmark_targets.json] [--summary FILE] [--out result.json]

Performance: the median over all runs given (CI alternates base and head on one runner so drift
hits both).  Fails if the head is more than max_slowdown slower than the base.

Gameplay: the matches are deterministic, so a difference is a real change in how the game plays.
Each stat with a 'real' band shows how far the game is from real football; the change fails if it
moves a stat further outside its band than the base was (by more than the stat's tolerance).
Stats inside the band may move freely.  'must' rules always apply.

Without base files (e.g. the base predates the benchmarks) it reports the head numbers only.
Exits 1 when a rule fails.
"""
import argparse
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load_all(paths):
    out = []
    for p in paths or []:
        if p and os.path.exists(p) and os.path.getsize(p) > 0:
            out.append(json.load(open(p)))
    return out


def get(d, dotted):
    for k in dotted.split("."):
        if not isinstance(d, dict) or k not in d:
            return None
        d = d[k]
    return d


def outside(v, band):
    lo, hi = band
    return lo - v if v < lo else v - hi if v > hi else 0.0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base-perf", nargs="*", default=[])
    ap.add_argument("--head-perf", nargs="*", default=[])
    ap.add_argument("--base-gameplay")
    ap.add_argument("--head-gameplay", required=True)
    ap.add_argument("--targets", default=os.path.join(HERE, "benchmark_targets.json"))
    ap.add_argument("--summary")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    T = json.load(open(a.targets))
    bp, hp = load_all(a.base_perf), load_all(a.head_perf)
    bg = load_all([a.base_gameplay])
    hg = load_all([a.head_gameplay])[0]
    bg = bg[0] if bg else None
    rows, fails = [], []

    lines = ["## Benchmarks: %s", ""]
    # ---- performance
    lines += ["### Performance (same runner, median of %d base / %d head runs)" % (len(bp), len(hp)), "",
              "| | measure | base | this change | change | limit |", "|---|---|---|---|---|---|"]
    for key, rule in T["performance"].items():
        h = statistics.median([get(x, key) for x in hp if get(x, key) is not None] or [0])
        b = statistics.median([get(x, key) for x in bp if get(x, key) is not None] or [0]) if bp else None
        if b:
            ch = h / b - 1
            ok = ch <= rule["max_slowdown"]
            if not ok:
                fails.append(rule["label"])
            lines.append("| %s | %s | %.1f | %.1f | %+.1f%% | <= +%.0f%% |" % (
                "✅" if ok else "❌", rule["label"], b, h, ch * 100, rule["max_slowdown"] * 100))
            rows.append(dict(kind="perf", key=key, base=b, head=h, change=ch, ok=ok))
        else:
            lines.append("| ➖ | %s | n/a | %.1f | | no base |" % (rule["label"], h))
            rows.append(dict(kind="perf", key=key, base=None, head=h, ok=True))

    # ---- gameplay
    hm = hg["per_match_mean"]
    bm = bg["per_match_mean"] if bg else None
    lines += ["", "### Gameplay (per 90-minute match, both teams, mean of %d AI-vs-AI matches)" % hg.get("matches", 0), "",
              "| | stat | real football | base | this change | gap to real |", "|---|---|---|---|---|---|"]
    for key, rule in T["gameplay"].items():
        h = hm.get(key)
        if h is None:
            continue
        band = rule["real"]
        gh = outside(h, band)
        b = bm.get(key) if bm else None
        ok = True
        if b is not None:
            gb = outside(b, band)
            ok = gh <= gb + rule["tolerance"]
        if not ok:
            fails.append("gameplay: " + key)
        status = "✅" if ok and gh == 0 else ("❌" if not ok else "🟡")
        gap = "in range" if gh == 0 else ("%.1f %s" % (gh, "below" if h < band[0] else "above"))
        lines.append("| %s | %s | %g–%g | %s | %.1f | %s |" % (
            status, key.replace("_", " "), band[0], band[1], "%.1f" % b if b is not None else "n/a", h, gap))
        rows.append(dict(kind="gameplay", key=key, base=b, head=h, band=band, gap=gh, ok=ok))

    # ---- must rules
    for key, rule in T.get("must", {}).items():
        h = get(hm, key) if "." not in key else get(hg, key)
        b = (get(bm, key) if "." not in key else get(bg, key)) if bg else None
        ok = True
        if h is None:
            continue
        if "min" in rule and h < rule["min"]:
            ok = False
        if "max_increase" in rule and b is not None and h > b + rule["max_increase"]:
            ok = False
        if not ok:
            fails.append(rule["label"])
        lines.append("| %s | %s | | %s | %s | must |" % ("✅" if ok else "❌", rule["label"],
                                                         "n/a" if b is None else round(b, 3), round(h, 3)))
        rows.append(dict(kind="must", key=key, base=b, head=h, ok=ok))

    lines[0] = lines[0] % ("no regressions" if not fails else "%d regression(s): %s" % (len(fails), ", ".join(fails)))
    lines += ["", "🟡 = not yet like real football, but no worse than the base. ❌ = worse than the base."]
    text = "\n".join(lines) + "\n"
    print(text)
    if a.summary:
        with open(a.summary, "a") as f:
            f.write(text)
    if a.out:
        json.dump(dict(passed=not fails, fails=fails, rows=rows), open(a.out, "w"), indent=1)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
