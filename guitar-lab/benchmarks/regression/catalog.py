"""Clip catalog. Audio that we cannot redistribute is optional and local.

Public clips (GuitarSet excerpts, rendered Karplus-Strong) are in the tree.
IDMT-SMT-Guitar is CC BY-NC-ND, so the wavs stay out of git. The Metallica
remaster and the user's AAC takes are local files, named below, also not in git.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
PRIVATE = DATA / 'private'
GUITARSET = DATA / 'guitarset'

# Player 05 (the split several GuitarSet papers hold out). CC BY 4.0.
GUITARSET_CLIPS = (
    {
        'id': 'gs_rock_solo',
        'category': 'solo_acoustic',
        'style': 'rock solo',
        'wav': '05_Rock1-90-C#_solo_mic.wav',
        'notes': '05_Rock1-90-C#_solo.notes.json',
        'sha256': '2e969753898c731a7e4e46935ff5f315d31acdaddf0a4ab9afa855a96307a9d8',
        'fast': True,
        'fast_window_s': 8.0,
    },
    {
        'id': 'gs_funk_solo',
        'category': 'solo_acoustic',
        'style': 'funk solo',
        'wav': '05_Funk1-114-Ab_solo_mic.wav',
        'notes': '05_Funk1-114-Ab_solo.notes.json',
        'sha256': '1bc53f0d2132e1d40efe3db88ae7c74ef53d256ed60a98dbed77270537307a1f',
        'fast': False,
    },
    {
        'id': 'gs_jazz_comp',
        'category': 'solo_acoustic',
        'style': 'jazz comping',
        'wav': '05_Jazz2-110-Bb_comp_mic.wav',
        'notes': '05_Jazz2-110-Bb_comp.notes.json',
        'sha256': '0ff82f67a72707cfa4f263aac890baeb9a11f50d0e1487c8f187a2e614b6bd9d',
        'fast': False,
    },
)

# IDMT-SMT-Guitar dataset 3: short electric-guitar DI pieces with note XML.
# Clean direct input, not an amplifier. CC BY-NC-ND: not committed.
IDMT_PIECES = (
    'nocturneNr2',
    'pathetique_mono',
    'pathetique_poly',
    'promenade_mono',
    'quintfall',
)

# Windows on take C's clock used by the older A-against-C comparison.
# Chosen from the active regions in the attached RESULTS (rests near 114–126 s
# and 235–248 s are outside). Not searched to maximise note F1.
# Take A and take C are separate performances, not a confirmed dry/wet pair.
# benchmarks/recordings is the behaviour lock and does not treat them as one.
USER_WINDOWS = ((30.0, 60.0), (150.0, 180.0))

RENDERED = (
    {'id': 'ks_clean_scale', 'category': 'rendered', 'voice': 'clean', 'fast': True},
    {'id': 'ks_dist_chug', 'category': 'rendered', 'voice': 'distorted', 'fast': True},
    {'id': 'ks_clear', 'category': 'reverb_clear', 'voice': 'clean', 'fast': True, 'pair': 'ks_reverb'},
    {'id': 'ks_reverb', 'category': 'reverb_clear', 'voice': 'reverb', 'fast': True, 'pair': 'ks_clear'},
)

# EGSet12: twelve miked-amp solos, no other effects. CC BY 4.0. Audio stays out of git.
# Guitar-TECHS P3: the twelve musical excerpts (miked amp and DI). CC BY 4.0.
# The other Guitar-TECHS archives (chords, scales, techniques) are not part of this gate.
EGSET12_IDS = tuple(f'{index:02d}' for index in range(1, 13))
GUITAR_TECHS_IDS = tuple(f'{index:02d}' for index in range(1, 13))
EGSET12_CLIPS = tuple(
    {'id': f'egset_{piece}', 'category': 'amp_solo', 'piece': piece}
    for piece in EGSET12_IDS
)
GUITAR_TECHS_CLIPS = tuple(
    {'id': f'techs_{piece}', 'category': 'amp_excerpt', 'piece': piece}
    for piece in GUITAR_TECHS_IDS
)


def _exists(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def guitarset_notes(path: Path):
    payload = json.loads(path.read_text())
    return payload['notes']


def idmt_dir():
    return PRIVATE / 'idmt' / 'dataset3'


def user_takes():
    """Local AAC paths for the older A-against-C comparison.

    The dict keys are historical. The files are not a confirmed dry/wet pair
    of one performance. The behaviour lock lives in ``benchmarks/recordings``.
    """
    folder = PRIVATE / 'user'
    return {
        'clear': folder / 'take_c_synth_4m58.aac',
        'reverb': folder / 'take_a_4m51.aac',
    }


def metallica_paths():
    folder = PRIVATE / 'metallica'
    return {'audio': folder / 'song.mp3', 'tab': folder / 'song.gp4'}


def egset12_dir():
    return PRIVATE / 'egset12'


def guitar_techs_dir():
    return PRIVATE / 'guitar_techs'


def _egset12_ready():
    folder = egset12_dir()
    return all(_exists(folder / f'{piece}.wav') and _exists(folder / f'{piece}.jams')
               for piece in EGSET12_IDS)


def _guitar_techs_ready():
    """Miked-amp and DI excerpts plus per-string MIDI. Room mics are not required."""
    root = guitar_techs_dir() / 'P3_music'
    return all(
        _exists(root / 'audio' / 'micamp' / f'micamp_{piece}.wav')
        and _exists(root / 'audio' / 'directinput' / f'directinput_{piece}.wav')
        and _exists(root / 'midi' / f'midi_{piece}.mid')
        for piece in GUITAR_TECHS_IDS
    )


def available_summary():
    """Which optional recordings are on disk. Does not open them."""
    idmt = idmt_dir()
    takes = user_takes()
    metal = metallica_paths()
    return {
        'guitarset': all(_exists(GUITARSET / c['wav']) for c in GUITARSET_CLIPS),
        'idmt': all(_exists(idmt / 'audio' / f'{name}.wav') and _exists(idmt / 'annotation' / f'{name}.xml')
                   for name in IDMT_PIECES),
        'user_reverb_pair': _exists(takes['clear']) and _exists(takes['reverb']),
        'metallica': _exists(metal['audio']) and _exists(metal['tab']),
        'carcassi_audio': False,
        'egdb': False,
        'egset12': _egset12_ready(),
        'guitar_techs': _guitar_techs_ready(),
    }
