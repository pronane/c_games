"""Slakh2100-redux from Zenodo to standard output, over many connections at once.

One connection gave 7 to 13 MB a second in the pilot; 16 ranged connections gave 33. The
pieces are written in order, so the output can be piped straight into ``tar xz``:

    python training/runpod/fetch_slakh.py 2>fetch.log | tar xz --no-same-owner -C <dir>

Slakh2100 is CC BY 4.0 (Manilow, Wichern, Seetharaman, Le Roux, WASPAA 2019).
"""
import sys
import time
import urllib.request
from collections import deque
from concurrent.futures import ThreadPoolExecutor

URL = 'https://zenodo.org/api/records/4599666/files/slakh2100_flac_redux.tar.gz/content'
SIZE = 104322767708
PIECE = 64 * 1024 * 1024
CONNECTIONS = 16


def fetch(i):
    a = i * PIECE
    b = min(SIZE, a + PIECE) - 1
    for attempt in range(40):
        try:
            request = urllib.request.Request(URL, headers={'Range': f'bytes={a}-{b}'})
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read()
            if len(data) == b - a + 1:
                return data
        except Exception as exc:
            print('retry', i, attempt, repr(exc)[:80], file=sys.stderr, flush=True)
        time.sleep(min(60, 3 * (attempt + 1)))
    raise SystemExit(f'piece {i} failed')


def main():
    pieces = (SIZE + PIECE - 1) // PIECE
    out = sys.stdout.buffer
    started = time.time()
    with ThreadPoolExecutor(CONNECTIONS) as pool:
        waiting, following = deque(), 0
        for done in range(pieces):
            while following < pieces and len(waiting) < 2 * CONNECTIONS:
                waiting.append(pool.submit(fetch, following))
                following += 1
            out.write(waiting.popleft().result())
            if done % 20 == 0:
                print(f'piece {done}/{pieces} {time.time() - started:.0f}s', file=sys.stderr, flush=True)
    out.flush()
    print('FETCH_COMPLETE', file=sys.stderr, flush=True)


if __name__ == '__main__':
    main()
