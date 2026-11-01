"""Plain-text (ASCII) guitar/bass tab -> timed notes, tab and MusicXML.

Most free tabs online are text like:

    e|-----0-----|-----3-----|
    B|---1---1---|---0---0---|
    G|-2-------2-|-0-------0-|
    ...

Text tab has frets and strings but no rhythm. Time is taken from horizontal position: each
bar line-to-bar line span is one bar of `beats_per_bar` beats, notes are placed in proportion
to their column and rounded to the nearest sixteenth. Without bar lines, the most common gap
between notes is taken as an eighth note. The tempo is whatever the player sets. Results say
so; they are a practice reference, not the composer's rhythm.
"""
from __future__ import annotations

import re

import numpy as np
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from . import song_analysis as sa
from .instruments import resolve_profile

router = APIRouter(prefix='/api/tabs')

# A tab line: optional string name, a bar/colon, then mostly dashes, digits and technique marks.
TAB_LINE = re.compile(r'^\s*([A-Ga-g][#b]?|\d)?\s*[|:]([-0-9xX|hpbr/\\~()<>.^=*sv\s]+)$')


def _tab_lines(text):
    """Runs of consecutive tab lines (one run = one system of the tab)."""
    runs, run = [], []
    for line in text.replace('\t', ' ').splitlines():
        m = TAB_LINE.match(line.rstrip())
        if m and m.group(2).count('-') >= 3:
            run.append(m.group(2).rstrip())
        else:
            if run:
                runs.append(run)
            run = []
    if run:
        runs.append(run)
    return runs


def parse_ascii_tab(text: str, open_strings: list[int], bpm: float = 90.0, beats_per_bar: int = 4):
    """open_strings: MIDI of each string from the highest (top tab line) to the lowest."""
    if not text or not text.strip():
        raise ValueError('The tab is empty.')
    strings = len(open_strings)
    systems, warnings = [], []
    for run in _tab_lines(text):
        if len(run) == strings:
            systems.append(run)
        elif len(run) > strings and len(run) % strings == 0:
            systems += [run[i:i+strings] for i in range(0, len(run), strings)]
        else:
            warnings.append(f'Skipped a block of {len(run)} tab lines; expected {strings} for this instrument.')
    if not systems:
        raise ValueError(f'No {strings}-line tab found. Each string needs its own line, like "e|--0--3--|".')

    beat = 60.0/bpm
    notes, bar_starts = [], []
    bar_index = 0.0                      # bars so far, in beats/beats_per_bar units
    for lines in systems:
        width = max(len(l) for l in lines)
        lines = [l.ljust(width, '-') for l in lines]
        # Bar lines are columns where every string has '|'.
        bars = [c for c in range(width) if all(l[c] == '|' for l in lines)]
        edges = [-1]+bars+[width]
        segments = [(a+1, b) for a, b in zip(edges[:-1], edges[1:]) if b-a > 2]
        events = []                      # (column, string index, fret)
        for s, line in enumerate(lines):
            c = 0
            while c < width:
                if line[c].isdigit():
                    j = c
                    while j < width and line[j].isdigit() and j-c < 2:
                        j += 1
                    events.append((c, s, int(line[c:j])))
                    c = j
                else:
                    c += 1
        if not events:
            bar_index += len(segments) or 1
            continue
        if not bars:
            # No bar lines: the most common gap between notes is an eighth note.
            cols = sorted({e[0] for e in events})
            gaps = np.diff(cols) if len(cols) > 1 else np.array([2])
            unit = float(np.median(gaps)) or 2.0
            for col, s, fret in events:
                beats_in = round((col-cols[0])/unit*.5*4)/4
                notes.append((bar_index*beats_per_bar+beats_in, s, fret))
            span = (cols[-1]-cols[0])/unit*.5+.5
            n_bars = max(1, int(np.ceil(span/beats_per_bar)))
            for b in range(n_bars):
                bar_starts.append(bar_index+b)
            bar_index += n_bars
            continue
        for a, b in segments:
            bar_starts.append(bar_index)
            inside = [e for e in events if a <= e[0] < b]
            # Writers usually leave a dash or two after the bar line before beat one.
            lead = min((e[0] for e in inside), default=a)-a
            a2 = a+lead if lead <= 2 else a
            for col, s, fret in inside:
                if a <= col < b:
                    frac = (col-a2)/max(1, b-a2)
                    beats_in = min(beats_per_bar-.25, round(frac*beats_per_bar*4)/4)
                    notes.append((bar_index*beats_per_bar+beats_in, s, fret))
            bar_index += 1
    if not notes:
        raise ValueError('The tab has no fret numbers.')

    notes.sort()
    onsets = sorted({n[0] for n in notes})
    nxt = {t: (onsets[i+1] if i+1 < len(onsets) else t+1) for i, t in enumerate(onsets)}
    out = []
    for t, s, fret in notes:
        midi = open_strings[s]+fret
        out.append({'time': t*beat, 'duration': max(.25, nxt[t]-t)*beat*.95, 'midi': midi,
                    'string': s+1, 'fret': fret, 'amplitude': .8})
    # Same string, same moment: keep one.
    seen, unique = set(), []
    for n in out:
        k = (round(n['time'], 4), n['string'])
        if k not in seen:
            seen.add(k)
            unique.append(n)
    total_beats = bar_index*beats_per_bar
    beats = [i*beat for i in range(int(total_beats)+1)]
    if not any(all(l[c] == '|' for l in sys_) for sys_ in systems for c in range(min(len(l) for l in sys_))):
        warnings.append('No bar lines found: rhythm guessed from spacing.')
    warnings.append('Text tab has no rhythm; timing comes from spacing between bar lines and is rounded to sixteenths.')
    return {'notes': unique, 'bars': [b*beats_per_bar*beat for b in bar_starts], 'beats': beats,
            'bpm': bpm, 'warnings': warnings}


def key_from_notes(notes):
    hist = np.zeros(12)
    for n in notes:
        hist[n['midi'] % 12] += n['duration']
    return sa.estimate_key(hist) if hist.sum() else None


class TextTab(BaseModel):
    text: str = Field(max_length=200_000)
    instrument: str = Field(default='guitar', max_length=20)
    tuning: str = Field(default='standard', max_length=40)
    capo: int = Field(default=0, ge=0, le=12)
    bpm: float = Field(default=90, ge=20, le=320)
    title: str = Field(default='Uploaded tab', max_length=120)


@router.post('/text')
def text_tab(body: TextTab, x_fretwork_client: str | None = Header(None)):
    if x_fretwork_client != 'studio':
        raise HTTPException(403, 'Use the studio client header.')
    try:
        profile = resolve_profile(body.instrument, body.tuning, body.capo)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if not profile['open_strings']:
        raise HTTPException(422, 'Text tab needs a stringed instrument (guitar or bass).')
    try:
        parsed = parse_ascii_tab(body.text, profile['open_strings'], body.bpm)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    key = key_from_notes(parsed['notes'])
    clef = 'bass' if body.instrument == 'bass' else 'treble8vb'
    xml = sa.musicxml(parsed['notes'], parsed['beats'], key, profile['open_strings'], title=body.title,
                      part_name=profile['name'], tab=True, clef=clef)
    return dict(parsed, key=key, musicxml=xml, instrument_profile=profile)
