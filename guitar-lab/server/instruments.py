"""The same JSON catalogue is consumed by the TypeScript studio and Python engine."""
import json
from pathlib import Path

CATALOGUE = json.loads((Path(__file__).resolve().parents[1]/'shared/instruments.json').read_text())


def resolve_profile(instrument='guitar', tuning='standard', capo=0, notation=None):
    base = next((p for p in CATALOGUE if p['id'] == instrument), None)
    if base is None:
        raise ValueError('Unknown instrument profile.')
    if type(capo) is not int or not 0 <= capo <= 12 or (not base['supports_capo'] and capo):
        raise ValueError('Invalid capo for this instrument.')
    if base['tunings']:
        if tuning not in base['tunings']:
            raise ValueError('Unsupported instrument tuning.')
        strings = [m+capo for m in base['tunings'][tuning]]
    else:
        if tuning not in ('none', 'standard'):
            raise ValueError('Piano does not support string tuning presets.')
        tuning, strings = 'none', []
    notation = notation or base['default_notation']
    if notation not in base['notations']:
        raise ValueError('Unsupported notation for this instrument.')
    return {**base, 'tuning': tuning, 'capo': capo, 'notation': notation, 'open_strings': strings,
            'max_fret': 24-capo,
            'midi_min': min(strings) if strings else base['midi_min'],
            'midi_max': min(base['midi_max'], max(base['tunings'][tuning])+24) if strings else base['midi_max']}
