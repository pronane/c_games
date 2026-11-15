import json

import numpy as np
import soundfile as sf

from benchmarks.fullband import gate


def _result(**f1):
    items = {k: {'f1': v, 'mix_sha256': f'mix-{k}', 'reference_sha256': f'ref-{k}'} for k, v in f1.items()}
    return {'items': items, 'mean_f1': sum(f1.values()) / len(f1), 'model_sha256': 'released-model'}


def test_a_candidate_passes_only_with_a_clear_gain_and_no_item_falling():
    base = _result(a=0.20, b=0.40, c=0.60)
    assert gate.verdict(base, _result(a=0.30, b=0.46, c=0.62))['passes']
    # A better mean that sacrifices one song does not pass.
    fell = gate.verdict(base, _result(a=0.45, b=0.55, c=0.50))
    assert not fell['passes'] and list(fell['items_that_fell']) == ['c']
    # Nor does a gain too small to tell from noise, or a candidate scored on fewer songs.
    assert not gate.verdict(base, _result(a=0.22, b=0.42, c=0.62))['passes']
    missing = gate.verdict(base, _result(a=0.40, b=0.60))
    assert missing['items_missing'] == ['c'] and not missing['passes']


def test_mean_uses_only_frozen_items_and_extra_items_fail():
    base = _result(a=0.20, b=0.40, c=0.60)
    # Same frozen scores, plus one perfect new item. The inflated mean must not pass.
    padded = _result(a=0.20, b=0.40, c=0.60, easy=1.0)
    padded['mean_f1'] = 1.0
    decision = gate.verdict(base, padded)
    assert decision['items_extra'] == ['easy']
    assert decision['mean_gain'] == 0.0
    assert not decision['passes']


def test_changed_mix_or_reference_fails_and_baseline_is_not_overwritten(tmp_path):
    base = _result(a=0.20, b=0.40)
    moved = _result(a=0.40, b=0.55)
    moved['items']['a']['mix_sha256'] = 'different-mix'
    decision = gate.verdict(base, moved)
    assert decision['items_changed'] == [{'item': 'a', 'field': 'mix_sha256'}]
    assert not decision['passes']
    path = tmp_path / 'baseline.json'
    gate.write_baseline({'items': {}}, path)
    try:
        gate.write_baseline({'items': {'later': {}}}, path)
    except SystemExit as exc:
        assert 'already exists' in str(exc)
    else:
        raise AssertionError('a second baseline write must stop')
    assert json.loads(path.read_text()) == {'items': {}}


def test_scoring_uses_the_app_transcribe_path_and_records_file_hashes(tmp_path, monkeypatch):
    folder = tmp_path / 'song'
    folder.mkdir()
    sf.write(folder / 'mix.wav', np.zeros((1600, 2), np.float32), 16000)
    (folder / 'reference.json').write_text(json.dumps({
        'notes': [{'time': 0.1, 'duration': 0.2, 'midi': 64}],
        'scored_from_s': 0.0, 'scored_to_s': 2.0,
    }))
    seen = {}

    def fake_transcribe(path, midi_min=40, midi_max=88, backend=None, **kwargs):
        seen['path'] = str(path)
        seen['midi_min'] = midi_min
        seen['midi_max'] = midi_max
        seen['backend'] = backend
        return [{'time': 0.1, 'duration': 0.2, 'midi': 64}]

    monkeypatch.setattr('server.models.transcribe', fake_transcribe)
    monkeypatch.setattr(gate, 'separated', lambda item: item / 'mix.wav')
    monkeypatch.setattr(gate, 'model_sha256', lambda: 'model-bytes')
    result = gate.score_items(data=tmp_path)
    from server.instruments import resolve_profile
    profile = resolve_profile('guitar')
    assert seen['backend'] == 'riley'
    assert seen['midi_min'] == profile['midi_min'] and seen['midi_max'] == profile['midi_max']
    assert result['model_sha256'] == 'model-bytes'
    assert result['items']['song']['mix_sha256'] == gate.file_sha256(folder / 'mix.wav')
    assert result['items']['song']['reference_sha256'] == gate.file_sha256(folder / 'reference.json')
    assert result['items']['song']['f1'] == 1.0
