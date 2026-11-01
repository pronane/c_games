"""One separation model on either device; never silently change quality.

CPU is the default. A request can ask for the graphics card ("gpu"): NVIDIA CUDA, else Apple
MPS. A GPU request falls back to CPU only for known memory / unsupported-operation errors,
with the same model and settings, and says so in the result.
"""
from functools import lru_cache
import os

DEFAULT_POLICY = 'cpu'
CHOICES = ('cpu', 'gpu')


def default_policy():
    return os.getenv('FRETWORK_DEVICE', DEFAULT_POLICY)


def select_device(torch, policy=None):
    policy = policy or default_policy()
    if policy not in ('auto', 'cpu', 'cuda', 'mps'):
        raise ValueError('FRETWORK_DEVICE must be auto, cpu, cuda or mps')
    if policy == 'cpu':
        return 'cpu'
    if policy in ('auto', 'cuda') and torch.cuda.is_available():
        return 'cuda'
    if policy == 'cuda':
        raise RuntimeError('CUDA was requested but is unavailable')
    mps = getattr(torch.backends, 'mps', None)
    if policy in ('auto', 'mps') and mps and mps.is_available():
        return 'mps'
    if policy == 'mps':
        raise RuntimeError('Apple MPS was requested but is unavailable')
    return 'cpu'


@lru_cache(maxsize=1)
def gpu_info():
    """What graphics card the server could use for separation, if any. Never raises."""
    try:
        import torch
    except Exception:
        return {'available': False, 'kind': None, 'name': None, 'detail': 'PyTorch is not installed.'}
    try:
        if torch.cuda.is_available():
            return {'available': True, 'kind': 'cuda', 'name': torch.cuda.get_device_name(0), 'detail': 'NVIDIA CUDA'}
        mps = getattr(torch.backends, 'mps', None)
        if mps and mps.is_available():
            return {'available': True, 'kind': 'mps', 'name': 'Apple GPU', 'detail': 'Apple Metal (MPS)'}
    except Exception as exc:
        return {'available': False, 'kind': None, 'name': None, 'detail': f'GPU check failed: {exc}'}
    return {'available': False, 'kind': None, 'name': None,
            'detail': 'No NVIDIA (CUDA) or Apple (MPS) graphics card is usable by this server.'}


def policy_for(choice):
    """Map the user's toggle to a device policy. 'gpu' needs a usable graphics card."""
    choice = (choice or 'cpu').lower()
    if choice not in CHOICES:
        raise ValueError('Processing must be "cpu" or "gpu".')
    if choice == 'cpu':
        return 'cpu'
    if not gpu_info()['available']:
        raise ValueError('No graphics card is available on the analysis server. Use CPU.')
    return 'auto'


def run_with_fallback(operation, torch, policy=None):
    policy = policy or default_policy()
    device = select_device(torch, policy)
    try:
        return operation(device), device, None
    except RuntimeError as exc:
        # Only known backend capability/memory failures justify retrying on CPU.
        message = str(exc).lower()
        recoverable = any(s in message for s in ('out of memory', 'not implemented for', 'not supported on mps', 'not currently implemented for the mps'))
        if device == 'cpu' or policy != 'auto' or not recoverable:
            raise
        if device == 'cuda':
            torch.cuda.empty_cache()
        return operation('cpu'), 'cpu', f'{device} memory/operation limit; retried the same model on CPU.'
