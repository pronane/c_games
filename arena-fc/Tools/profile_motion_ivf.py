#!/usr/bin/env python3
"""Profile deterministic flat-IVF candidate scans against exact motion matching.

This is an offline quality/work-count study, not a runtime backend. It compares the
same weighted normalized feature and continuity costs as Core MotionDatabase.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "Data" / "clips" / "motion_features.json"
SWITCH_PENALTY = 0.08
TEMPORAL_PENALTY = 0.12


def squared_distance(a, b):
    total = 0.0
    for x, y in zip(a, b):
        delta = x - y
        total += delta * delta
    return total


def circle_distance(a, b):
    delta = math.fmod(a - b, 1.0)
    if delta > 0.5:
        delta -= 1.0
    if delta < -0.5:
        delta += 1.0
    return abs(delta)


def deterministic_kmeans(points, k, iterations=30):
    """Farthest-first init + stable Lloyd updates; no RNG or parallel reductions."""
    if not points or k <= 0:
        raise ValueError("k-means needs points and a positive k")
    k = min(k, len(points))
    centers = [list(points[0])]
    nearest = [squared_distance(point, centers[0]) for point in points]
    while len(centers) < k:
        chosen = max(range(len(points)), key=lambda i: (nearest[i], -i))
        centers.append(list(points[chosen]))
        center = centers[-1]
        for i, point in enumerate(points):
            nearest[i] = min(nearest[i], squared_distance(point, center))

    assignments = [-1] * len(points)
    for _ in range(iterations):
        next_assignments = []
        sums = [[0.0] * len(points[0]) for _ in centers]
        counts = [0] * len(centers)
        for i, point in enumerate(points):
            cluster = min(range(len(centers)), key=lambda c: (squared_distance(point, centers[c]), c))
            next_assignments.append(cluster)
            counts[cluster] += 1
            for d, value in enumerate(point):
                sums[cluster][d] += value
        changed = next_assignments != assignments
        assignments = next_assignments
        for c, count in enumerate(counts):
            if count:
                centers[c] = [value / count for value in sums[c]]
        if not changed:
            break
    return centers, assignments


def make_queries(rows, vectors):
    """Pair current pose features with a different clip's desired future trajectory."""
    clips = sorted({row["clipId"] for row in rows})
    by_clip = {clip: [] for clip in clips}
    for index, row in enumerate(rows):
        by_clip[row["clipId"]].append(index)
    clip_index = {clip: i for i, clip in enumerate(clips)}
    queries = []
    for i, row in enumerate(rows):
        source_clip = row["clipId"]
        source_clip_i = clip_index[source_clip]
        target_clip = clips[(source_clip_i + 1) % len(clips)]
        target_rows = by_clip[target_clip]
        target_index = target_rows[i % len(target_rows)]
        query = list(vectors[i])
        query[11:23] = vectors[target_index][11:23]
        queries.append({
            "vector": query,
            "ballState": row["ballState"],
            "clipId": source_clip,
            "phase": row["phase"],
        })
    return queries


def choose_ball_rows(rows, ball):
    matching = [i for i, row in enumerate(rows) if row["ballState"] == ball]
    if matching:
        return matching
    neutral = [i for i, row in enumerate(rows) if row["ballState"] == "None"]
    return neutral if neutral else list(range(len(rows)))


def gameplay_cost(query, row, vector, row_vector):
    cost = squared_distance(vector, row_vector)
    if query["clipId"]:
        if query["clipId"] != row["clipId"]:
            cost += SWITCH_PENALTY
        else:
            cost += TEMPORAL_PENALTY * circle_distance(query["phase"], row["phase"])
    return cost


def run_exact(rows, vectors, queries):
    results = []
    candidate_total = 0
    start = time.perf_counter()
    for query in queries:
        candidates = choose_ball_rows(rows, query["ballState"])
        candidate_total += len(candidates)
        winner = min(candidates, key=lambda i: (gameplay_cost(query, rows[i], query["vector"], vectors[i]), i))
        results.append(winner)
    elapsed = time.perf_counter() - start
    return results, elapsed, candidate_total / len(queries)


def run_ivf(rows, vectors, queries, exact, k, nprobe, exact_candidates_per_query):
    centers, assignments = deterministic_kmeans(vectors, k)
    lists = [[] for _ in centers]
    for row_index, cell in enumerate(assignments):
        lists[cell].append(row_index)
    wins = 0
    exact_hits = 0
    scanned = 0
    visited = 0
    start = time.perf_counter()
    for qi, query in enumerate(queries):
        ranked_cells = sorted(range(len(centers)), key=lambda c: (squared_distance(query["vector"], centers[c]), c))
        selected = ranked_cells[:min(nprobe, len(ranked_cells))]
        visited += sum(len(lists[cell]) for cell in selected)
        eligible = set(choose_ball_rows(rows, query["ballState"]))
        candidates = [i for cell in selected for i in lists[cell] if i in eligible]
        scanned += len(candidates)
        if exact[qi] in candidates:
            exact_hits += 1
        if candidates:
            winner = min(candidates, key=lambda i: (gameplay_cost(query, rows[i], query["vector"], vectors[i]), i))
            wins += winner == exact[qi]
    elapsed = time.perf_counter() - start
    return {
        "recall": wins / len(queries),
        "winner_recall": wins / len(queries),
        "exact_hit_recall": exact_hits / len(queries),
        "avg_scanned": scanned / len(queries),
        "avg_rows_visited": visited / len(queries),
        "work_fraction": ((len(centers) + scanned / len(queries)) / exact_candidates_per_query),
        "mean_ms": elapsed * 1000 / len(queries),
        "max_list": max(map(len, lists)),
        "mean_list": len(rows) / len(lists),
        "lists": len(lists),
    }


def profile(path, ks, nprobes):
    data = json.loads(path.read_text())
    if data.get("featureSchemaVersion") not in (1, 2):
        raise ValueError("Only motion feature schemas v1/v2 are supported")
    dims = data["dimensions"]
    # v2 also holds one-shot entry rows; this profile is about the gait search.
    rows = [r for r in data["rows"] if r.get("category", "Locomotion") == "Locomotion"]
    mean = data["normalization"]["mean"]
    std = data["normalization"]["stdDev"]
    weights = data["weights"]
    vectors = []
    for row in rows:
        vectors.append([((row["features"][d] - mean[d]) / std[d]) * math.sqrt(weights[d])
                        for d in range(dims)])
    queries = make_queries(rows, vectors)
    exact, exact_elapsed, exact_candidates = run_exact(rows, vectors, queries)
    print(f"Feature DB: {len(rows)} rows x {dims} dims; deterministic paired-trajectory queries: {len(queries)}")
    print(f"Exact scan: {exact_candidates:.1f} context-eligible features/query, {exact_elapsed*1000/len(queries):.4f} ms/query in Python reference")
    print(" Kc  nprobe  visited  feat-scan  max-list  winner-recall  distance-work  py-ms/query")
    results = []
    for k in ks:
        for nprobe in nprobes:
            result = run_ivf(rows, vectors, queries, exact, k, nprobe, exact_candidates)
            result["k"] = k; result["nprobe"] = nprobe
            results.append(result)
            print(f"{k:3d} {nprobe:7d} {result['avg_rows_visited']:8.1f} {result['avg_scanned']:9.1f} {result['max_list']:9d}"
                  f" {result['winner_recall']:13.3%} {result['work_fraction']:14.3%} {result['mean_ms']:12.4f}")
    return rows, dims, results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--k", type=int, nargs="+", default=[1, 4, 8, 16, 32, 64, 128])
    parser.add_argument("--nprobe", type=int, nargs="+", default=[1, 2, 4, 8, 16])
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    rows, dims, results = profile(args.db, args.k, args.nprobe)
    if args.json_out:
        payload = {"rows": len(rows), "dimensions": dims, "results": results}
        args.json_out.write_text(json.dumps(payload, indent=2) + "\n")
        print(f"wrote {args.json_out}")


if __name__ == "__main__":
    main()
