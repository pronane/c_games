"""One separation model on either device; never silently change quality."""
import os


def select_device(torch, policy=None):
    policy = policy or os.getenv('FRETWORK_DEVICE', 'auto')
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


def run_with_fallback(operation, torch):
    device = select_device(torch)
    try:
        return operation(device), device, None
    except RuntimeError as exc:
        # Only known backend capability/memory failures justify retrying on CPU.
        message = str(exc).lower()
        recoverable = any(s in message for s in ('out of memory', 'not implemented for', 'not supported on mps', 'not currently implemented for the mps'))
        if device == 'cpu' or os.getenv('FRETWORK_DEVICE', 'auto') != 'auto' or not recoverable:
            raise
        if device == 'cuda':
            torch.cuda.empty_cache()
        return operation('cpu'), 'cpu', f'{device} memory/operation limit; retried the same model on CPU.'
