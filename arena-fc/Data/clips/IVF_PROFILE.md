# Flat-IVF profile for the current motion table

## Recommendation

**Keep the exact `MotionDatabase` scan; do not enable IVF yet.** The current table is
only 403 rows × 23 dimensions. Context filtering leaves an average of 250.4 rows for
feature-distance evaluation in this test. An exact scan is small, has 100% recall, and
avoids centroid training, extra index data, and approximate misses.

If the table grows enough that exact Core profiling identifies feature distance as a
bottleneck, start experiments at **Kc=32, nprobe=4**. On this probe set it retained
91.6% of exact winners while evaluating 36.2% as many feature vectors plus centroid
comparisons. Treat that as a speed/quality candidate, not a ship setting. For a
higher-recall bias, Kc=16, nprobe=4 reached 92.8% at 56.1% distance work. Kc=8,
nprobe=4 reached 98.5% but did essentially all of the exact work, so it had no useful
scan reduction.

## Reproduce

```sh
python3 Tools/profile_motion_ivf.py
```

The script uses the checked-in schema-v1 feature table, weighted z-score coordinates,
fixed farthest-first centroid initialization, stable Lloyd updates, stable centroid
and row tie-breaks, and the same switch/temporal penalties as the Core float search.
It tries Kc values 1, 4, 8, 16, 32, 64, 128 and nprobe values 1, 2, 4, 8, 16.

The 403 deterministic probes combine a row's current pose/root features with a
neighboring clip's future trajectory, while retaining the source row's ball-state,
current clip, and phase for exact context/continuity scoring. They are synthetic
coverage probes, not captured live-game queries.

## Results

`feature work` is `(Kc centroid distances + context-eligible candidate distances) /
average exact candidate distances`. `visited` includes all rows in selected lists;
`feat scan` counts rows that survive the hard ball-state filter. Winner recall is the
fraction of probes whose exact best `(clipId, frameIndex)` was also selected by IVF.

| Kc | nprobe | Avg rows visited | Avg feature scan | Max list | Exact-winner recall | Feature work vs exact |
|---:|---:|---:|---:|---:|---:|---:|
| exact | — | 403.0 | 250.4 | — | 100.0% | 100.0% |
| 8 | 1 | 151.0 | 117.8 | 216 | 75.7% | 50.3% |
| 8 | 2 | 227.3 | 159.1 | 216 | 85.6% | 66.7% |
| 8 | 4 | 380.3 | 241.8 | 216 | 98.5% | 99.7% |
| 16 | 1 | 48.5 | 34.8 | 108 | 73.4% | 20.3% |
| 16 | 4 | 191.1 | 124.4 | 108 | 92.8% | 56.1% |
| 16 | 8 | 317.2 | 207.8 | 108 | 93.3% | 89.4% |
| 32 | 1 | 20.0 | 13.1 | 62 | 69.7% | 18.0% |
| 32 | 2 | 38.5 | 27.2 | 62 | 83.1% | 23.6% |
| 32 | 4 | 83.6 | 58.5 | 62 | 91.6% | 36.2% |
| 32 | 8 | 161.6 | 101.9 | 62 | 93.3% | 53.5% |
| 64 | 4 | 40.5 | 27.7 | 62 | 85.4% | 36.6% |
| 64 | 8 | 91.9 | 62.3 | 62 | 92.6% | 50.4% |
| 128 | 8 | 31.6 | 21.8 | 62 | 91.3% | 59.8% |

The reference Python loop measured roughly 0.40 ms/query for exact and 0.16 ms/query
for Kc=32/nprobe=4 in this sandbox. These timings are not representative of the C#
Core runtime; the operation counts and recall are the meaningful comparison here.

## Interpretation / limits

- The 403-row corpus is below the usual range where IVF pays off. At 60 Hz for 22
  players, the exact candidate-distance loop is about 7.6 million feature-dimension
  operations per second before compiler/runtime optimizations.
- Kc=32/nprobe=4 saves distance evaluations but misses about 8.4% of exact winners on
  these synthetic probes. Raising nprobe improves recall but quickly gives back the
  scan savings.
- The list imbalance (for example, max list 62 at Kc=32 or 64) shows that increasing
  Kc alone is not a reliable fix for this small, multimodal dataset.
- No IVF/PQ/OPQ data or runtime code is introduced. Re-profile with captured MotionQuery
  values and a larger corpus, then compare in the C# runtime before selecting an index.
