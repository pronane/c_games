"""Real model adapters. Missing dependencies/weights are blocking, never fake output."""
import importlib.util
import os
from pathlib import Path
import numpy as np
from .devices import run_with_fallback, default_policy, gpu_info
from .model_store import model_repo, checkpoint_status, EXPECTED_SHA256, DOWNLOAD_URL


class ModelUnavailable(RuntimeError):
    pass


def transcription_path():
    configured = os.environ.get('FRETWORK_BASIC_PITCH_MODEL')
    if configured:
        return Path(configured)
    spec = importlib.util.find_spec('basic_pitch')
    return Path(spec.origin).parent/'saved_models/icassp_2022/nmp.onnx' if spec and spec.origin else Path('/nonexistent')


def capabilities():
    # Configuration is not proof that inference will succeed. Actual loading errors
    # are surfaced on the job. Health intentionally does not download models.
    demucs = importlib.util.find_spec('demucs') is not None
    basic = importlib.util.find_spec('basic_pitch') is not None
    repo = model_repo()
    weights_valid, weight_detail = checkpoint_status(repo)
    runtime = demucs and importlib.util.find_spec('torch') is not None and importlib.util.find_spec('torchaudio') is not None
    transcription = transcription_path()
    return {
        'separation': {'configured': runtime and weights_valid, 'model': 'htdemucs_6s', 'guitar_capable': True, 'stems': ['guitar', 'bass', 'piano'],
                       'runtime_installed': runtime, 'weights_verified': weights_valid,
                       'detail': weight_detail if runtime else 'Install Demucs, torch and torchaudio. '+weight_detail,
                       'download_url': DOWNLOAD_URL,
                       'installation_supported': os.getenv('FRETWORK_ALLOW_MODEL_INSTALL') == '1'},
        'transcription': {'configured': basic and importlib.util.find_spec('onnxruntime') is not None and transcription.is_file(), 'model': 'Basic Pitch ONNX',
                          'detail': 'Requires Basic Pitch and ONNX Runtime; uses bundled nmp.onnx or FRETWORK_BASIC_PITCH_MODEL.'},
        'device_policy': default_policy(),
        'gpu': gpu_info(),
    }


def separate_guitar(audio, sr, policy=None):
    return separate_stem(audio, sr, 'guitar', policy)


def separate_instrument(audio, sr, stem, policy=None):
    # Keep the original adapter available to older clients/tests.
    return separate_guitar(audio, sr, policy) if stem == 'guitar' else separate_stem(audio, sr, stem, policy)


def _load_six_stem_model():
    from demucs.pretrained import get_model
    return get_model('htdemucs_6s', repo=model_repo())


def run_demucs(audio, sr, policy=None):
    """Run the pinned six-source model once. Returns ({source: (n, 2) float32}, samplerate, provenance)."""
    if not capabilities()['separation']['configured']:
        raise ModelUnavailable('Instrument separation is not configured. Install Demucs and provision the local htdemucs_6s weights; see server/README.md.')
    import torch
    import torchaudio
    from demucs.apply import apply_model
    model = _load_six_stem_model()
    model.eval()
    x = torch.from_numpy(np.asarray(audio, dtype=np.float32).T.copy()).float()
    if x.shape[0] == 1:
        x = x.repeat(2, 1)
    x = torchaudio.functional.resample(x, sr, model.samplerate)
    mean, std = x.mean(), x.std().clamp_min(1e-8)
    normal = (x - mean) / std

    def infer(device):
        model.to(device)
        torch.manual_seed(0)
        # Same model, shifts, overlap and float32 on CPU/GPU.
        with torch.inference_mode():
            stems = apply_model(model, normal[None].to(device), device=device,
                                shifts=1, split=True, overlap=.25, progress=False)[0]
        return {name: (stems[i].detach().cpu() * std + mean).numpy().T.astype(np.float32)
                for i, name in enumerate(model.sources)}

    output, device, warning = run_with_fallback(infer, torch, policy)
    return output, model.samplerate, {'model': 'htdemucs_6s', 'sources': list(model.sources), 'device': device,
                                      'warning': warning, 'sha256': EXPECTED_SHA256,
                                      'quality': 'Uncalibrated; human listening approval required.'}


def separate_stem(audio, sr, stem, policy=None):
    if stem not in ('guitar', 'bass', 'piano'):
        raise ValueError('Unsupported separation stem.')
    stems, rate, provenance = run_demucs(audio, sr, policy)
    if stem not in stems:
        raise ModelUnavailable(f'Configured model has no dedicated {stem} output. An other stem is not accepted.')
    return stems[stem], rate, dict(provenance, stem=stem)


# Basic Pitch's library defaults (0.5/0.3) roughly tripled the note count on plucked guitar
# (harmonics, ringing notes re-triggered). 0.7/0.5 raised onset+pitch F1 from 0.48 to 0.86
# on an isolated test part and 0.50 to 0.72 on a separated stem. Validate on real recordings.
ONSET_THRESHOLD = float(os.getenv('FRETWORK_ONSET_THRESHOLD', '0.7'))
FRAME_THRESHOLD = float(os.getenv('FRETWORK_FRAME_THRESHOLD', '0.5'))


# Overdrive smears onsets and spreads energy into harmonics, so Basic Pitch's onset confidence
# drops on driven guitar and real notes fall under the clean thresholds. Measured on a
# multi-guitar tab rendered clean / crunch / high-gain (note F1, 50 ms onsets): high gain
# solo .56 -> .67 and rhythm .45 -> .58 at 0.5/0.3; crunch solo .61 -> .68 at 0.6/0.4 with
# rhythm unchanged. 'auto' trusts the tone guess less (it is a heuristic), so it only moves
# halfway. Clean stays at the GuitarSet-tuned defaults.
TONE_THRESHOLDS = {'clean': None, 'crunch': (0.6, 0.4), 'distorted': (0.5, 0.3), 'auto-distorted': (0.6, 0.4)}


def thresholds_for(tone: str | None, chosen_by_user: bool):
    key = tone if chosen_by_user or tone != 'distorted' else 'auto-distorted'
    return TONE_THRESHOLDS.get(key) or (ONSET_THRESHOLD, FRAME_THRESHOLD)


def transcribe(path, midi_min=40, midi_max=88, posteriors=False, thresholds=None):
    """Note events; with posteriors=True also Basic Pitch's per-frame onset/note activations
    ({'onset', 'note': (frames, 88) arrays, pitch index = MIDI-21, 'hop': seconds per frame})."""
    if not capabilities()['transcription']['configured']:
        raise ModelUnavailable('Specialist transcription is not configured. Install Basic Pitch ONNX and provision nmp.onnx; see server/README.md.')
    from basic_pitch.inference import predict
    output, _, events = predict(str(path), model_or_model_path=str(transcription_path()),
                           onset_threshold=(thresholds or (ONSET_THRESHOLD, FRAME_THRESHOLD))[0],
                           frame_threshold=(thresholds or (ONSET_THRESHOLD, FRAME_THRESHOLD))[1], minimum_note_length=100,
                           minimum_frequency=440*2**((midi_min-69)/12), maximum_frequency=440*2**((midi_max-69)/12))
    import soundfile as sf
    duration = sf.info(path).duration
    notes = [{'id': i, 'time': float(max(onset, 0)), 'duration': float(min(end, duration)-max(onset, 0)), 'midi': int(pitch),
              'amplitude': float(amplitude)} for i, (onset, end, pitch, amplitude, _) in enumerate(events) if midi_min <= int(pitch) <= midi_max and min(end, duration) > max(onset, 0)]
    notes = sorted(notes, key=lambda n: (n['time'], n['midi']))
    if posteriors:
        from basic_pitch.constants import ANNOTATION_HOP
        return notes, {'onset': np.asarray(output['onset']), 'note': np.asarray(output['note']), 'hop': ANNOTATION_HOP}
    return notes


def transcribe_profile(path, profile, posteriors=False):
    if profile['transcription_method'] != 'basic_pitch_onnx':
        raise ModelUnavailable('The selected transcription method is not implemented; no substitute was used.')
    if posteriors:
        return transcribe(path, midi_min=profile['midi_min'], midi_max=profile['midi_max'], posteriors=True)
    return transcribe(path, midi_min=profile['midi_min'], midi_max=profile['midi_max'])
