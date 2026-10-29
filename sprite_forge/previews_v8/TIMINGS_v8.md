# Timings: v7 vs v8 (same box, same inputs, 8 CPU cores, no GPU)

`python tools/bench_v8.py <studio dir> out.json` - each scenario run with an empty cache ('first'), then the same command again ('rebuild'), then with one move changed (v8 only).

| scenario | v7 first | v8 first | v7 rebuild | v8 rebuild | v8 one move changed |
|---|---|---|---|---|---|
| spec fighter14 + SNES console | 4.0 s | 1.5 s (x2.6) | 3.9 s | 0.2 s (x17) | 1.2 s |
| photo fighter14 | 3.0 s | 2.0 s (x1.5) | 3.1 s | 0.2 s (x17) | - |
| library rig fighter14 (3D render) | 4.4 s | 1.4 s (x3.1) | 4.4 s | 0.2 s (x20) | - |
| mannequin gaelic36 + GLB + FBX | 11.7 s | 3.5 s (x3.4) | 11.4 s | 0.3 s (x34) | 2.5 s |
| video -> sprites (2 clips) | 5.7 s | 4.6 s (x1.2) | 5.7 s | 1.0 s (x6) | - |
| UI quick preview (fighter14 draft) | 3.7 s | 0.3 s (x12.9) | - | - | - |

Side-on photo fighter (a real-photo cut-out, not shipped; `--turn 90`, 14 Egyptian Fighter moves, 672x800, from `tools/test_v8.py`):

| | time |
|---|---|
| v8 final, thread pool | 19.3 s |
| v8 final, SFS_THREADS=1 (serial, one core) | 46.8 s |
| v8 rebuild unchanged (cache) | 0.8 s |
| v8 Quick preview (draft) | 2.3 s |

Notes: v7 has no cache, so its rebuild costs the same as a first build. 'UI quick preview' in v7 is a full build (v7 has no draft mode). Thread-pool output is pixel-identical to serial output (tested). Times vary +-10% run to run.
