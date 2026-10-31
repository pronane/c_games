"""Real ONNX model smoke test. Skipped when optional runtime/weights are absent."""
import numpy as np
import pytest
import soundfile as sf
from server.models import capabilities, transcribe


@pytest.mark.skipif(not capabilities()['transcription']['configured'], reason='Install optional ONNX transcription runtime')
def test_actual_basic_pitch_detects_a3(tmp_path):
    path = tmp_path/'a3.wav'
    t = np.arange(44100*2)/44100
    sf.write(path, .3*np.sin(2*np.pi*220*t)*np.minimum(t*20, 1), 44100)
    notes = transcribe(path)
    assert any(n['midi'] == 57 and n['duration'] > .5 for n in notes)
    assert all(0 <= n['time'] < 2 and n['time']+n['duration'] <= 2.001 for n in notes)


def test_actual_separation_when_explicitly_enabled():
    """No synthetic substitute: requires real checkpoint and opt-in CPU/GPU time."""
    import os
    from server.models import separate_guitar
    if os.getenv('FRETWORK_RUN_SEPARATION_TEST') != '1':
        pytest.skip('Set FRETWORK_RUN_SEPARATION_TEST=1 to run the heavyweight real model')
    if not capabilities()['separation']['configured']:
        pytest.fail('Real separation test requested, but approved runtime/weights are absent')
    sr = 44100
    t = np.arange(sr)/sr
    mixed = (.15*np.sin(2*np.pi*220*t)+.15*np.sin(2*np.pi*55*t)).astype(np.float32)
    guitar, output_sr, provenance = separate_guitar(mixed[:, None], sr)
    assert provenance['model'] == 'htdemucs_6s'
    assert provenance['sha256'].startswith('34c22ccb')
    assert guitar.shape == (sr, 2) and output_sr == sr
    assert np.isfinite(guitar).all()
