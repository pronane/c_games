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
                 two_hop_threshold=0.25, min_direct_valid=4, valid_target=4,
                 bridge_budget=2, query_bridge_cap=16, second_hop_cap=512):
    """Best-first layer-0 search with stable, non-returnable adaptive bridges."""
    eligible_set = set(eligible)
    dist_evals = 0
    predicate_checks = 0
    seen = set()
    # (distance, row id, returnable); false entries can be expanded but never reranked.
    frontier = []
    hits = {}
    query_bridges = 0
    bridge_expansions = 0

    def add(node, returnable, known_distance=None):
        nonlocal dist_evals
        if node in seen:
            return False
        seen.add(node)
        if known_distance is None:
            dist_evals += 1
            known_distance = squared_distance(query["vector"], vectors[node])
        frontier.append((known_distance, node, returnable))
        if returnable:
            hits[node] = known_distance
        return True

    predicate_checks += 1
    entry_valid = entry in eligible_set
    if mode == "strict" and not entry_valid:
        return [], dist_evals, predicate_checks, 0, len(seen), 0, 0
    add(entry, entry_valid)
    expansions = 0
    while frontier and expansions < ef:
        frontier.sort(key=lambda item: (item[0], item[1]))
        _, node, returnable = frontier.pop(0)
        expansions += 1
        if mode == "racorn" and not returnable:
            bridge_expansions += 1
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
            # The adaptive target counts only new, unique legal candidates from this expand.
            new_valid = 0
            for neighbor in direct_valid:
                new_valid += int(add(neighbor, True))
            invalid_fraction = len(direct_invalid) / max(1, len(neighbors))
            two_hop = invalid_fraction >= two_hop_threshold and len(direct_valid) < min_direct_valid
            if two_hop:
                examined = 0
                for middle in neighbors:  # illegal middle nodes are paths, not hits
                    for endpoint in adjacency[middle]:
                        if endpoint == node or endpoint in seen:
                            continue
                        examined += 1
                        predicate_checks += 1
                        if endpoint in eligible_set:
                            new_valid += int(add(endpoint, True))
                        if examined >= second_hop_cap or new_valid >= valid_target:
                            break
                    if examined >= second_hop_cap or new_valid >= valid_target:
                        break

            # Adaptive fallback occurs only after direct and conditional two-hop checks.
            if mode == "racorn" and new_valid < valid_target and query_bridges < query_bridge_cap:
                deficit = valid_target - new_valid
                allowance = min(deficit, bridge_budget, query_bridge_cap - query_bridges)
                illegal = [node_id for node_id in direct_invalid if node_id not in seen]
                # Rank only bridge candidates; row id is the deterministic tie break.
                bridge_distances = []
                for node_id in illegal:
                    dist_evals += 1
                    bridge_distances.append((squared_distance(query["vector"], vectors[node_id]), node_id))
                bridge_distances.sort(key=lambda item: (item[0], item[1]))
                for bridge_distance, bridge in bridge_distances[:allowance]:
                    if add(bridge, False, bridge_distance):
                        query_bridges += 1
        else:
            raise ValueError(f"unknown search mode {mode}")

    # HNSW-style bounded candidate result set, then full Core continuity-aware rerank.
    candidates = sorted(hits, key=lambda i: (hits[i], i))[:max(1, ef)]
    candidates.sort(key=lambda i: (gameplay_cost(query, rows[i], query["vector"], vectors[i]), i))
    return candidates, dist_evals, predicate_checks, expansions, len(seen), query_bridges, bridge_expansions


def profile(db_path, degree=16, efs=(8, 16, 32, 64), min_partition_size=1000,
            bridge_target=4, bridge_budget=2, query_bridge_cap=16):
    data = json.loads(db_path.read_text())
    rows = data["rows"]
    vectors = normalized_vectors(data)
    queries = make_queries(rows, vectors)
    exact, exact_candidates = exact_winners(rows, vectors, queries)
    adjacency, entry, _ = build_knn_graph(vectors, degree)

    modes = ("postfilter", "strict", "soft", "acorn1", "racorn")
    print(f"DB {len(rows)}x{data['dimensions']}; graph degree={degree}; entry={entry}; probes={len(queries)}")
    print(f"Exact filtered oracle averages {exact_candidates:.1f} legal distance candidates/query")
    print(f"RACORN ASF: valid_target={bridge_target}, per-expand budget={bridge_budget}, query cap={query_bridge_cap}")
    print("mode       ef   recall@1  no-result  dist-evals  pred-checks  expansions  bridge-add/exp  result-cands")
    results = []
    per_tag_at_max_ef = {}
    max_ef = max(efs)
    for mode in modes:
        for ef in efs:
            hits = 0
            empty = 0
            evals = predicates = expansions = result_count = bridge_adds = bridge_expands = 0
            start = time.perf_counter()
            for qi, query in enumerate(queries):
                eligible = choose_ball_rows(rows, query["ballState"])
                candidates, n_dist, n_pred, n_expand, _, n_bridge_adds, n_bridge_expands = graph_search(
                    rows, vectors, adjacency, entry, query, eligible, ef, mode,
                    valid_target=bridge_target, bridge_budget=bridge_budget,
                    query_bridge_cap=query_bridge_cap)
                if any(candidate not in eligible for candidate in candidates):
                    raise AssertionError("A filtered-out bridge leaked into the result set")
                if n_bridge_adds > query_bridge_cap:
                    raise AssertionError("RACORN query bridge cap was exceeded")
                evals += n_dist; predicates += n_pred; expansions += n_expand
                bridge_adds += n_bridge_adds; bridge_expands += n_bridge_expands
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
                "bridgeAdds": bridge_adds / len(queries),
                "bridgeExpansions": bridge_expands / len(queries),
                "resultCandidates": result_count / len(queries),
                "pythonMsPerQuery": elapsed * 1000 / len(queries),
            }
            results.append(result)
            print(f"{mode:10s} {ef:3d} {result['recallAt1']:9.3%} {result['noResultRate']:10.3%}"
                  f" {result['distanceEvals']:11.1f} {result['predicateChecks']:12.1f}"
                  f" {result['expansions']:11.1f} {result['bridgeAdds']:6.1f}/{result['bridgeExpansions']:<6.1f}"
                  f" {result['resultCandidates']:13.1f}")

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
            "bridgeTarget": bridge_target, "bridgeBudget": bridge_budget,
            "queryBridgeCap": query_bridge_cap, "results": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--degree", type=int, default=16)
    parser.add_argument("--ef", type=int, nargs="+", default=[8, 16, 32, 64])
    parser.add_argument("--min-partition-size", type=int, default=1000)
    parser.add_argument("--bridge-target", type=int, default=4)
    parser.add_argument("--bridge-budget", type=int, default=2)
    parser.add_argument("--query-bridge-cap", type=int, default=16)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    report = profile(args.db, args.degree, tuple(args.ef), args.min_partition_size,
                     args.bridge_target, args.bridge_budget, args.query_bridge_cap)
    if args.json_out:
        args.json_out.write_text(json.dumps(report, indent=2) + "\n")
        print(f"wrote {args.json_out}")


if __name__ == "__main__":
    main()
