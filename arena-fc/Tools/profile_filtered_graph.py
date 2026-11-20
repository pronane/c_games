#!/usr/bin/env python3
"""Compare hard-filter search policies on a deterministic flat proximity graph.

This is an algorithmic probe, not a production multilayer HNSW implementation. It
isolates post-filter, strict, soft-bridge, ACORN-1-style two-hop, and RACORN-style
fallback behavior using the current AME feature table and exact filtered oracle.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

from profile_motion_ivf import choose_ball_rows, gameplay_cost, make_queries, squared_distance

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "Data" / "clips" / "motion_features.json"


def normalized_vectors(data):
    mean = data["normalization"]["mean"]
    std = data["normalization"]["stdDev"]
    weights = data["weights"]
    return [[((row["features"][d] - mean[d]) / std[d]) * math.sqrt(weights[d])
             for d in range(data["dimensions"])] for row in data["rows"]]


def build_knn_graph(vectors, degree):
    """Deterministic symmetrized KNN graph and centroid-nearest entry node."""
    n = len(vectors)
    directed = []
    edges = [set() for _ in vectors]
    for i, vector in enumerate(vectors):
        nearest = sorted((squared_distance(vector, vectors[j]), j)
                         for j in range(n) if j != i)[:min(degree, n - 1)]
        directed.append([j for _, j in nearest])
        for _, j in nearest:
            edges[i].add(j)
            edges[j].add(i)
    centroid = [sum(row[d] for row in vectors) / n for d in range(len(vectors[0]))]
    entry = min(range(n), key=lambda i: (squared_distance(vectors[i], centroid), i))
    return [tuple(sorted(neighbors)) for neighbors in edges], entry, directed


def exact_winners(rows, vectors, queries):
    winners = []
    candidate_counts = []
    for query in queries:
        candidates = choose_ball_rows(rows, query["ballState"])
        candidate_counts.append(len(candidates))
        winner = min(candidates, key=lambda i: (gameplay_cost(query, rows[i], query["vector"], vectors[i]), i))
        winners.append(winner)
    return winners, sum(candidate_counts) / len(candidate_counts)


def graph_search(rows, vectors, adjacency, entry, query, eligible, ef, mode,
                 two_hop_threshold=0.25, min_direct_valid=4, bridge_target=4,
                 bridge_budget=2, second_hop_cap=512):
    """Best-first layer-0 search with filter policies and deterministic tie breaks."""
    eligible_set = set(eligible)
    dist_evals = 0
    predicate_checks = 0
    seen = set()
    # (distance, row id, returnable). An illegal soft bridge is expandable only.
    frontier = []
    hits = {}

    def add(node, returnable):
        nonlocal dist_evals
        if node in seen:
            return False
        seen.add(node)
        dist_evals += 1
        distance = squared_distance(query["vector"], vectors[node])
        frontier.append((distance, node, returnable))
        if returnable:
            hits[node] = distance
        return True

    predicate_checks += 1
    entry_valid = entry in eligible_set
    if mode == "strict" and not entry_valid:
        return [], dist_evals, predicate_checks, 0, len(seen)
    # Illegal entry points may guide traversal, but post-filter hits are still legal only.
    add(entry, entry_valid)
    expansions = 0
    while frontier and expansions < ef:
        frontier.sort(key=lambda item: (item[0], item[1]))
        _, node, _ = frontier.pop(0)
        expansions += 1
        neighbors = adjacency[node]
        direct_valid = []
        direct_invalid = []
        for neighbor in neighbors:
            predicate_checks += 1
            (direct_valid if neighbor in eligible_set else direct_invalid).append(neighbor)

        if mode == "postfilter":
            for neighbor in neighbors:
                add(neighbor, neighbor in eligible_set)
        elif mode == "strict":
            for neighbor in direct_valid:
                add(neighbor, True)
        elif mode == "soft":
            for neighbor in direct_valid:
                add(neighbor, True)
            for neighbor in direct_invalid:
                add(neighbor, False)
        elif mode in ("acorn1", "racorn"):
            added_valid = 0
            for neighbor in direct_valid:
                added_valid += int(add(neighbor, True))
            invalid_fraction = len(direct_invalid) / max(1, len(neighbors))
            two_hop = invalid_fraction >= two_hop_threshold and len(direct_valid) < min_direct_valid
            if two_hop:
                examined = 0
                for middle in neighbors:
                    for endpoint in adjacency[middle]:
                        if endpoint == node or endpoint in seen:
                            continue
                        examined += 1
                        predicate_checks += 1
                        if endpoint in eligible_set:
                            added_valid += int(add(endpoint, True))
                        if examined >= second_hop_cap or added_valid >= max(ef // 2, min_direct_valid):
                            break
                    if examined >= second_hop_cap or added_valid >= max(ef // 2, min_direct_valid):
                        break
            if mode == "racorn" and added_valid < bridge_target:
                bridges_added = 0
                for bridge in direct_invalid:  # neighbors are already in stable row-id order
                    if add(bridge, False):
                        bridges_added += 1
                    if bridges_added >= bridge_budget:
                        break
        else:
            raise ValueError(f"unknown search mode {mode}")

    # HNSW-style bounded candidate result set, then full Core continuity-aware rerank.
    candidates = sorted(hits, key=lambda i: (hits[i], i))[:max(1, ef)]
    candidates.sort(key=lambda i: (gameplay_cost(query, rows[i], query["vector"], vectors[i]), i))
    return candidates, dist_evals, predicate_checks, expansions, len(seen)


def profile(db_path, degree=16, efs=(8, 16, 32, 64), min_partition_size=1000):
    data = json.loads(db_path.read_text())
    rows = data["rows"]
    vectors = normalized_vectors(data)
    queries = make_queries(rows, vectors)
    exact, exact_candidates = exact_winners(rows, vectors, queries)
    adjacency, entry, _ = build_knn_graph(vectors, degree)

    modes = ("postfilter", "strict", "soft", "acorn1", "racorn")
    print(f"DB {len(rows)}x{data['dimensions']}; graph degree={degree}; entry={entry}; probes={len(queries)}")
    print(f"Exact filtered oracle averages {exact_candidates:.1f} legal distance candidates/query")
    print("mode       ef   recall@1  no-result  dist-evals  pred-checks  expansions  result-cands")
    results = []
    per_tag_at_max_ef = {}
    max_ef = max(efs)
    for mode in modes:
        for ef in efs:
            hits = 0
            empty = 0
            evals = predicates = expansions = result_count = 0
            start = time.perf_counter()
            for qi, query in enumerate(queries):
                eligible = choose_ball_rows(rows, query["ballState"])
                candidates, n_dist, n_pred, n_expand, _ = graph_search(
                    rows, vectors, adjacency, entry, query, eligible, ef, mode)
                evals += n_dist; predicates += n_pred; expansions += n_expand
                result_count += len(candidates)
                tag = query["ballState"]
                if ef == max_ef:
                    if (mode, tag) not in per_tag_at_max_ef:
                        per_tag_at_max_ef[(mode, tag)] = [0, 0, 0]
                    per_tag_at_max_ef[(mode, tag)][0] += 1
                if not candidates:
                    empty += 1
                    if ef == max_ef: per_tag_at_max_ef[(mode, tag)][2] += 1
                elif candidates[0] == exact[qi]:
                    hits += 1
                    if ef == max_ef: per_tag_at_max_ef[(mode, tag)][1] += 1
            elapsed = time.perf_counter() - start
            result = {
                "mode": mode, "ef": ef,
                "recallAt1": hits / len(queries),
                "noResultRate": empty / len(queries),
                "distanceEvals": evals / len(queries),
                "predicateChecks": predicates / len(queries),
                "expansions": expansions / len(queries),
                "resultCandidates": result_count / len(queries),
                "pythonMsPerQuery": elapsed * 1000 / len(queries),
            }
            results.append(result)
            print(f"{mode:10s} {ef:3d} {result['recallAt1']:9.3%} {result['noResultRate']:10.3%}"
                  f" {result['distanceEvals']:11.1f} {result['predicateChecks']:12.1f}"
                  f" {result['expansions']:11.1f} {result['resultCandidates']:13.1f}")

    print(f"\nPer-filter results at ef={max_ef}:")
    print("mode       BallState   queries  recall@1  no-result")
    for (mode, tag), (count, hits, empty) in sorted(per_tag_at_max_ef.items()):
        print(f"{mode:10s} {tag:11s} {count:7d} {hits/max(1,count):9.3%} {empty/max(1,count):10.3%}")

    # Hard-filter graph shards below the specified floor use exact float search.
    partitions = {}
    for i, row in enumerate(rows):
        partitions.setdefault(row["ballState"], []).append(i)
    fallback_costs = []
    all_small = all(len(shard) < min_partition_size for shard in partitions.values())
    for query in queries:
        shard = partitions.get(query["ballState"], [])
        if len(shard) < min_partition_size:
            fallback_costs.append(len(shard))
        else:
            fallback_costs.append(0)
    print("\nPartition policy:")
    for tag, shard in sorted(partitions.items()):
        policy = "exact fallback" if len(shard) < min_partition_size else "per-tag graph"
        print(f"  BallState={tag:11s} rows={len(shard):3d}: {policy}")
    if all_small:
        # Every query uses the exact fallback, which equals the filtered oracle.
        print(f"  exact-fallback winner recall=100.000%, avg feature candidates={sum(fallback_costs)/len(fallback_costs):.1f}")
    else:
        print("  At least one shard meets the graph threshold; per-shard graph recall requires follow-up profiling.")
    return {"rows": len(rows), "dimensions": data["dimensions"], "degree": degree,
            "efValues": list(efs), "minPartitionSize": min_partition_size,
            "results": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--degree", type=int, default=16)
    parser.add_argument("--ef", type=int, nargs="+", default=[8, 16, 32, 64])
    parser.add_argument("--min-partition-size", type=int, default=1000)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    report = profile(args.db, args.degree, tuple(args.ef), args.min_partition_size)
    if args.json_out:
        args.json_out.write_text(json.dumps(report, indent=2) + "\n")
        print(f"wrote {args.json_out}")


if __name__ == "__main__":
    main()
