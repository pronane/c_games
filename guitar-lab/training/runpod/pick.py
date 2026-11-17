"""Compare sweep.py outputs fairly: threshold chosen on every second song, score on the rest.

    python training/runpod/pick.py <released sweep log> <other sweep log> [...]
"""
import json
import statistics as st
import sys


def rows(path):
    return {json.loads(line)['track']: json.loads(line) for line in open(path) if line.startswith('{')}


def main(paths):
    logs = {p: rows(p) for p in paths}
    common = sorted(set.intersection(*(set(r) for r in logs.values())))
    choose, report = common[1::2], common[0::2]
    base = logs[paths[0]]
    out = {'songs': len(common)}
    for src in ('true_stem', 'separated', 'mix'):
        out[src] = {}
        picked = {}
        for path, R in logs.items():
            ths = list(R[common[0]][src])
            best = max(ths, key=lambda th: st.mean(R[t][src][th][0] for t in choose))
            picked[path] = best
            f, p, r = (round(st.mean(R[t][src][best][i] for t in report), 3) for i in range(3))
            out[src][path] = {'threshold': float(best), 'f1': f, 'precision': p, 'recall': r,
                              'f1_by_threshold_all_songs': {th: round(st.mean(R[t][src][th][0] for t in common), 3) for th in ths}}
        for path, R in list(logs.items())[1:]:
            out[src][path]['songs_ahead_of_first'] = sum(R[t][src][picked[path]][0] > base[t][src][picked[paths[0]]][0] for t in common)
    print(json.dumps(out, indent=1))


if __name__ == '__main__':
    main(sys.argv[1:])
