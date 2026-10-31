"""Real model adapters. Missing dependencies/weights are blocking, never fake output."""
import importlib.util
import os
from pathlib import Path
import numpy as np
from .devices import run_with_fallback
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
        'separation': {'configured': runtime and weights_valid, 'model': 'htdemucs_6s', 'guitar_capable': True,
                       'runtime_installed': runtime, 'weights_verified': weights_valid,
                       'detail': weight_detail if runtime else 'Install Demucs, torch and torchaudio. '+weight_detail,
                       'download_url': DOWNLOAD_URL,
                       'installation_supported': os.getenv('FRETWORK_ALLOW_MODEL_INSTALL') == '1'},
        'transcription': {'configured': basic and importlib.util.find_spec('onnxruntime') is not None and transcription.is_file(), 'model': 'Basic Pitch ONNX',
                          'detail': 'Requires Basic Pitch and ONNX Runtime; uses bundled nmp.onnx or FRETWORK_BASIC_PITCH_MODEL.'},
        'device_policy': os.getenv('FRETWORK_DEVICE', 'auto'),
    }


def separate_guitar(audio, sr):
    if not capabilities()['separation']['configured']:
        raise ModelUnavailable('Guitar separation is not configured. Install Demucs and provision the local htdemucs_6s weights; see server/README.md.')
    import torch
    import torchaudio
    from demucs.pretrained import get_model
    from demucs.apply import apply_model
    repo = model_repo()
    model = get_model('htdemucs_6s', repo=repo)
    if 'guitar' not in model.sources:
        raise ModelUnavailable('Configured model has no dedicated guitar output. An other stem is not accepted.')
    model.eval()
    x = torch.from_numpy(audio.T.copy()).float()
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
        guitar = stems[model.sources.index('guitar')].detach().cpu() * std + mean
        return guitar.numpy().T

    output, device, warning = run_with_fallback(infer, torch)
    return output, model.samplerate, {'model': 'htdemucs_6s', 'device': device, 'warning': warning,
                                      'sha256': EXPECTED_SHA256,
                                      'quality': 'Uncalibrated; human listening approval required.'}


def transcribe(path):
    if not capabilities()['transcription']['configured']:
        raise ModelUnavailable('Specialist transcription is not configured. Install Basic Pitch ONNX and provision nmp.onnx; see server/README.md.')
    from basic_pitch.inference import predict
    _, _, events = predict(str(path), model_or_model_path=str(transcription_path()),
                           onset_threshold=.5, frame_threshold=.3, minimum_note_length=100,
                           minimum_frequency=65, maximum_frequency=1400)
    import soundfile as sf
    duration = sf.info(path).duration
    notes = [{'id': i, 'time': float(max(onset, 0)), 'duration': float(min(end, duration)-max(onset, 0)), 'midi': int(pitch),
              'amplitude': float(amplitude)} for i, (onset, end, pitch, amplitude, _) in enumerate(events) if 40 <= int(pitch) <= 88 and min(end, duration) > max(onset, 0)]
    return sorted(notes, key=lambda n: (n['time'], n['midi']))
