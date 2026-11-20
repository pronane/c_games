# Filtered graph search profile

## Recommendation

For the current AME table, **use exact search with hard tag filtering**. Do not add a
filtered HNSW/ACORN/RACORN runtime backend yet. The feature database has 403 rows and
its three BallState partitions contain only 31, 62, and 310 rows; following the design
floor of 1,000 rows, every partition should use exact float search. This has exact
filtered recall and avoids graph construction, traversal, bridges, and approximate
misses.

If a single graph becomes a requirement later, no tested filter policy was robust
across all tags: soft bridges tied post-filter overall, while ACORN-1-style two-hop
used fewer feature-distance evaluations at high ef but did not improve the difficult
Contested partition. The adaptive RACORN-style fallback injected an average 15.5
bridges/query and expanded 11.7 at ef=64, yet did not improve aggregate or Contested
recall; it also increased predicate checks. A real multilayer HNSW implementation and
captured query data should be profiled before considering any of these for shipping.

## Reproduce

```sh
python3 Tools/profile_filtered_graph.py
```

The deterministic probe set and weighted z-score features are shared with
`profile_motion_ivf.py`. Ground truth is an exact scan over the legal BallState rows
using feature distance plus the same switch and temporal costs as Core. Queries combine
one row's current pose/root features with another clip's desired future trajectory.
They are synthetic coverage probes, not live gameplay captures.

The experimental graph is a **single-layer symmetrized 16-nearest-neighbour graph**,
with deterministic KNN construction and a centroid-nearest entry. The traversal compares
post-filter, strict valid-only, soft-bridge, conditional ACORN-1-style two-hop, and
RACORN-style budgeted bridge behavior. Its fallback target is four new legal candidates
per expansion; after direct and conditional two-hop discovery it injects up to two
illegal 1-hop neighbours, ranked by query distance then row ID, with a 16-bridge
per-query cap. Bridges enter only the expansion frontier, never the result pool.

This is a filter-policy experiment, **not a multilayer production HNSW benchmark**.
ef is the maximum number of node expansions.

## Corpus and filtered recall

| BallState | Rows | Selectivity |
|---|---:|---:|
| None | 310 | 76.9% |
| Possessed | 62 | 15.4% |
| Contested | 31 | 7.7% |

Exact search evaluates an average of 250.4 legal feature candidates per probe. At ef=64:

| Search policy | Exact-winner recall | No-result rate | Distance evaluations/query | Predicate checks/query | Bridges added / expanded |
|---|---:|---:|---:|---:|---:|
| Exact filtered scan | 100.0% | 0.0% | 250.4 | — | — |
| Global graph, post-filter | 77.4% | 7.7% | 152.5 | 1,246.7 | — |
| Global graph, strict filter | 62.0% | 23.1% | 96.8 | 940.6 | — |
| Global graph, soft bridges | 77.4% | 7.7% | 152.5 | 1,246.7 | — |
| ACORN-1-style two-hop | 77.4% | 7.7% | 106.5 | 1,182.5 | — |
| RACORN-style fallback | 77.4% | 7.7% | 146.7 | 1,801.3 | 15.5 / 11.7 |
| Per-tag exact fallback (all shards < 1,000) | 100.0% | 0.0% | 250.4 | — | — |

At ef=64, the global graph's per-filter results were:

| Policy | None recall | Possessed recall | Contested recall | Contested no-result |
|---|---:|---:|---:|---:|
| Post-filter | 80.6% | 100.0% | 0.0% | 100.0% |
| Strict | 80.6% | 0.0% | 0.0% | 100.0% |
| Soft bridges | 80.6% | 100.0% | 0.0% | 100.0% |
| ACORN-1-style | 80.6% | 100.0% | 0.0% | 100.0% |
| RACORN-style | 80.6% | 100.0% | 0.0% | 100.0% |

Increasing ef from 8 to 64 raised aggregate recall gradually but did not repair the
Contested partition. The one-graph experiment demonstrates the filter-induced
connectivity problem described in the design notes; two-hop expansion and bridges did
not make this small ambient graph reliably navigable for that tag.

## Interpretation / limits

- Tag partitioning is the clean fit for these known, low-cardinality hard filters. All
  current shards are below the 1,000-row floor, so per the stated policy, exact search
  is the intended backend within every shard.
- Strict valid-only expansion can strand the search at an illegal entry or in a
  disconnected valid subgraph. Soft bridges avoid some strict-search starvation, but
  matched post-filter results and still missed many exact winners.
- ACORN-1-style two-hop reduced feature-distance evaluations versus soft bridges at
  ef=64, but added predicate checks and retained the same recall/no-result rates.
  RACORN-style fallback filled its bridge budget frequently but did not improve recall;
  query-distance ordering did not recover Contested hits in this graph.
- These are deterministic algorithmic counts on synthetic queries, not C# timings or
  a production HNSW recall guarantee. No runtime HNSW/ACORN/RACORN code or one-shot
  index entries are introduced.
