"""The GOAT helper refuses to develop on official test items and skips uncropped charts."""
from pathlib import Path

import pytest

from benchmarks.goat.score import discover, score_split
from benchmarks.goat.split import (
    DIAGNOSTIC_TEST, OFFICIAL_TEST, PRIMARY_TEST, HeldOutItem, primary, require_development, split_of,
)


def test_official_test_ids_and_the_diagnostic_item():
    assert OFFICIAL_TEST == (35, 60, 103, 118, 152, 156, 166)
    assert 60 in DIAGNOSTIC_TEST and 60 not in PRIMARY_TEST
    assert set(PRIMARY_TEST) == set(OFFICIAL_TEST) - {60}
    assert split_of(4) == 'train' and split_of(35) == 'test'
    assert primary(156) and not primary(60)


def test_development_refuses_every_official_test_item():
    require_development([4, 5, 46, 101])
    with pytest.raises(HeldOutItem):
        require_development([4, 35])
    with pytest.raises(HeldOutItem):
        require_development([60])


def test_discovery_uses_the_crop_clock_and_skips_the_uncropped_chart(tmp_path):
    crop = tmp_path / 'GOAT' / 'data' / 'item_35' / 'audio_and_midi_crop'
    full = tmp_path / 'GOAT' / 'data' / 'item_35' / 'original_full_references'
    crop.mkdir(parents=True)
    full.mkdir(parents=True)
    (crop / 'item_35_fine_aligned.mid').write_bytes(b'crop')
    (full / 'item_35_fine_aligned.mid').write_bytes(b'full')
    found = list(discover(tmp_path))
    assert len(found) == 1
    _item, folder, midi = found[0]
    assert folder == crop and midi.name == 'item_35_fine_aligned.mid'
    assert 'original_full_references' not in Path(midi).parts


def test_train_split_does_not_score_a_held_out_item(tmp_path, monkeypatch):
    crop = tmp_path / 'GOAT' / 'data' / 'item_35' / 'audio_and_midi_crop'
    crop.mkdir(parents=True)
    (crop / 'item_35_fine_aligned.mid').write_bytes(b'crop')

    def fail(*_args, **_kwargs):
        raise AssertionError('held-out audio was scored')

    monkeypatch.setattr('benchmarks.goat.score.score_item', fail)
    assert score_split(tmp_path, 'train', frame_join=False) == []
