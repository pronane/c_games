import numpy as np
import pytest

from training.finetune_riley import assign_songs, prepare_workers, require_trainable, song_id, split_files


def test_song_id_groups_segments_of_one_track():
    assert song_id('slakh:separated:Track00021') == 'Track00021'
    assert song_id('slakh:mix:Track00021') == 'Track00021'
    assert song_id('guitarset:clean:00_Funk1') == '00_Funk1'
    assert song_id('riff:4') == 'riff:4'
    assert song_id('riff') == 'riff'


def test_validation_holds_out_whole_songs():
    groups = {
        'TrackA': ['a0', 'a1', 'a2'],
        'TrackB': ['b0', 'b1'],
        'TrackC': ['c0'],
    }
    val, train = assign_songs(groups, val_target=2, order=['TrackA', 'TrackB', 'TrackC'])
    assert val == ['a0', 'a1', 'a2']
    assert train == ['b0', 'b1', 'c0']
    assert set(val).isdisjoint(train)


def test_split_reads_sources_and_keeps_a_song_together(tmp_path):
    def write(name, source):
        path = tmp_path / name
        np.savez_compressed(path, source=np.array(source))
        return str(path)

    files = [
        write('seg_00000.npz', 'slakh:separated:TrackA'),
        write('seg_00001.npz', 'slakh:mix:TrackA'),
        write('seg_00002.npz', 'slakh:separated:TrackB'),
        write('seg_00003.npz', 'guitarset:crunch:clip9'),
    ]
    val, train = split_files(files, lambda path: str(np.load(path)['source']), val_target=2, rng=np.random.default_rng(0))
    songs = {}
    for path in val + train:
        songs.setdefault(song_id(str(np.load(path)['source'])), set()).add('val' if path in val else 'train')
    assert all(len(sides) == 1 for sides in songs.values())
    assert set(val).isdisjoint(train)
    assert len(val) >= 1 and len(train) >= 1


def test_one_song_and_an_empty_loader_stop(tmp_path):
    with pytest.raises(SystemExit, match='at least two songs'):
        assign_songs({'only': ['a', 'b']}, val_target=1)
    with pytest.raises(SystemExit, match='fewer than the batch size'):
        require_trainable(['one'], batch=4)


def test_workers_use_spawn_before_cuda_workers_start():
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    code = (
        'from training.finetune_riley import prepare_workers\n'
        'import torch.multiprocessing as mp\n'
        'prepare_workers(2)\n'
        'assert mp.get_start_method(allow_none=True) == "spawn"\n'
    )
    subprocess.check_call([sys.executable, '-c', code], cwd=root)
