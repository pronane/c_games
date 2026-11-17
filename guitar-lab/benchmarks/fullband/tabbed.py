"""Frozen full-band items from a song recording and its tab.

    python -m benchmarks.fullband.tabbed <name> <song audio> <tab.json> <line-up map.json> <guitar track numbers> [--stem <guitar stem>]

The reference is the tab's guitar notes, placed on the recording with a line-up made by
``server.tab_align.line_up`` (the map file). Unlike a play-along item, this reference is not
the engine's own reading, so it can show a model getting more notes right, not only losing
fewer to the band. Its timing is only as good as the line-up, and the tab may not match the
recording exactly, so absolute scores are low; the comparison between models is what counts.
Only the stretch the tab covers is scored.

``--stem`` reuses a guitar stem already separated by the app for this recording (saves the
separation); otherwise ``gate.py`` separates the mix the first time it scores the item.
Items are written to benchmarks/fullband/data/ (not committed).
"""
from __future__ import annotations

import argparse
import json
import shutil

import numpy as np
import soundfile as sf

from benchmarks.fullband.items import DATA, SR, load


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('name')
    ap.add_argument('song')
    ap.add_argument('tab')
    ap.add_argument('map')
    ap.add_argument('tracks', help='comma-separated tab track numbers that are guitar heard in the recording')
    ap.add_argument('--stem')
    a = ap.parse_args()
    from server import tab_align as ta
    tab = json.load(open(a.tab))
    mapping = json.load(open(a.map))
    wanted = {int(x) for x in a.tracks.split(',')}
    tracks = [{'name': t['name'], 'track': t['index'], 'notes': t['notes']} for t in tab['tracks'] if t['index'] in wanted]
    placed = ta.place_tracks(tracks, mapping)
    notes = sorted(({'time': round(float(n['time']), 4), 'duration': round(float(n.get('duration', 0.25)), 4), 'midi': int(n['midi'])}
                    for part in placed for n in part['notes']), key=lambda n: n['time'])
    mix = load(a.song)
    seconds = len(mix) / SR
    notes = [n for n in notes if 0 <= n['time'] < seconds]
    if len(notes) < 50:
        raise SystemExit(f'Only {len(notes)} tab notes fall inside the recording; check the map and track numbers.')
    folder = DATA / a.name
    folder.mkdir(parents=True, exist_ok=True)
    peak = float(np.abs(mix).max()) or 1.0
    sf.write(folder / 'mix.wav', mix / max(1.0, peak / 0.98), SR)
    (folder / 'guitar.wav').unlink(missing_ok=True)
    if a.stem:
        shutil.copyfile(a.stem, folder / 'guitar.wav')
    extra = {'kind': 'tab', 'tab_tracks': sorted(wanted), 'line_up_similarity': mapping.get('similarity'),
             'attack_match': mapping.get('attack_match'),
             'scored_from_s': round(max(0.0, notes[0]['time'] - 0.5), 2), 'scored_to_s': round(min(seconds, notes[-1]['time'] + 0.5), 2)}
    (folder / 'reference.json').write_text(json.dumps({'source': 'tab, lined up with the recording', 'notes': notes, **extra}))
    print(json.dumps({'item': a.name, 'seconds': round(seconds, 1), 'reference_notes': len(notes),
                      'line_up_similarity': extra['line_up_similarity']}))


if __name__ == '__main__':
    main()
