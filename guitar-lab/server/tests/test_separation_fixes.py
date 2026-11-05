"""Unit tests for demucs quality settings and stereo L/R transcription merge."""
import os
from pathlib import Path
from unittest import mock

import numpy as np
import pytest
import soundfile as sf

from server import models


def test_demucs_inference_settings_defaults(monkeypatch):
    monkeypatch.delenv('FRETWORK_DEMUCS_SHIFTS', raising=False)
    monkeypatch.delenv('FRETWORK_DEMUCS_OVERLAP', raising=False)
    assert models.demucs_inference_settings() == (2, 0.5)


def test_demucs_inference_settings_env_and_clamp(monkeypatch):
    monkeypatch.setenv('FRETWORK_DEMUCS_SHIFTS', '4')
    monkeypatch.setenv('FRETWORK_DEMUCS_OVERLAP', '0.25')
    assert models.demucs_inference_settings() == (4, 0.25)
    monkeypatch.setenv('FRETWORK_DEMUCS_SHIFTS', '0')
    monkeypatch.setenv('FRETWORK_DEMUCS_OVERLAP', '2')
    assert models.demucs_inference_settings() == (1, 0.99)


def test_merge_note_lists_collapses_near_duplicates():
    a = [{'id': 0, 'time': 1.0, 'duration': .2, 'midi': 60, 'amplitude': .4}]
    b = [{'id': 0, 'time': 1.02, 'duration': .3, 'midi': 60, 'amplitude': .9},
         {'id': 1, 'time': 2.0, 'duration': .2, 'midi': 64, 'amplitude': .5}]
    m = models.merge_note_lists(a, b, window=.04)
    assert len(m) == 2
    assert m[0]['midi'] == 60 and m[0]['amplitude'] == .9
    assert m[1]['midi'] == 64 and m[1]['id'] == 1


def test_stereo_tx_channels_requires_both_active():
    sr = 1000
    t = np.arange(sr) / sr
    tone = (.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    silent = np.zeros_like(tone)
    stereo = np.stack([tone, silent], axis=1)
    chans = models.stereo_tx_channels(stereo)
    assert len(chans) == 1 and chans[0][0] == 'mono'
    both = np.stack([tone, .5 * tone], axis=1)
    chans = models.stereo_tx_channels(both)
    assert [c[0] for c in chans] == ['L', 'R']


def test_transcribe_merges_lr_when_stereo(tmp_path, monkeypatch):
    monkeypatch.setenv('FRETWORK_LR_TRANSCRIBE', '1')
    path = tmp_path / 'stereo.wav'
    sr = 22050
    t = np.arange(sr) / sr
    L = (.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    R = (.2 * np.sin(2 * np.pi * 330 * t)).astype(np.float32)
    sf.write(path, np.stack([L, R], axis=1), sr)

    calls = []

    def fake_predict(p, midi_min, midi_max, thresholds):
        calls.append(Path(p).name)
        # L file -> A3 (57), R file -> E4 (64)
        if p.name.endswith('.L.wav'):
            notes = [{'id': 0, 'time': 0.1, 'duration': 0.5, 'midi': 57, 'amplitude': 0.8}]
        elif p.name.endswith('.R.wav'):
            notes = [{'id': 0, 'time': 0.12, 'duration': 0.5, 'midi': 64, 'amplitude': 0.7},
                     {'id': 1, 'time': 0.1, 'duration': 0.5, 'midi': 57, 'amplitude': 0.3}]
        else:
            notes = []
        return notes, {'onset': np.zeros((1, 88)), 'note': np.zeros((1, 88))}

    monkeypatch.setattr(models, 'capabilities', lambda: {
        'transcription': {'configured': True}, 'separation': {'configured': False},
    })
    monkeypatch.setattr(models, '_predict_file', fake_predict)
    notes = models.transcribe(path, midi_min=40, midi_max=88)
    assert any(n.endswith('.L.wav') for n in calls) and any(n.endswith('.R.wav') for n in calls)
    midis = sorted(n['midi'] for n in notes)
    assert midis == [57, 64]
    # louder L's 57 kept over quieter R duplicate
    a57 = next(n for n in notes if n['midi'] == 57)
    assert a57['amplitude'] == 0.8


def test_transcribe_can_disable_lr(tmp_path, monkeypatch):
    monkeypatch.setenv('FRETWORK_LR_TRANSCRIBE', '0')
    path = tmp_path / 'stereo.wav'
    sr = 8000
    t = np.arange(sr) / sr
    tone = (.2 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    sf.write(path, np.stack([tone, tone], axis=1), sr)
    calls = []

    def fake_predict(p, midi_min, midi_max, thresholds):
        calls.append(Path(p).name)
        return [{'id': 0, 'time': 0.1, 'duration': 0.4, 'midi': 57, 'amplitude': 0.5}], {}

    monkeypatch.setattr(models, 'capabilities', lambda: {
        'transcription': {'configured': True}, 'separation': {'configured': False},
    })
    monkeypatch.setattr(models, '_predict_file', fake_predict)
    notes = models.transcribe(path)
    assert calls == ['stereo.wav']
    assert len(notes) == 1
