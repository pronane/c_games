"""Provision only the pinned Demucs six-source checkpoint, never arbitrary pickle."""
import argparse
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import urllib.error
import urllib.request

MODEL_NAME = 'htdemucs_6s'
CHECKPOINT = '5c90dfd2-34c22ccb.th'
EXPECTED_SIZE = 54_996_327
EXPECTED_SHA256 = '34c22ccb381c6f9fdbf324f04e1e2fe21aaaf293f5ded163a162697ff9a02ddd'
# The full digest matches the Git LFS object ID for the official checkpoint.
DOWNLOAD_URL = ('https://github.com/nomadkaraoke/python-audio-separator/releases/'
                'download/model-configs/' + CHECKPOINT)
BAG_CONTENT = "models: ['5c90dfd2']\n"


class InvalidCheckpoint(ValueError):
    pass


def model_repo():
    configured = os.getenv('FRETWORK_DEMUCS_REPO')
    return Path(configured).expanduser() if configured else Path(__file__).resolve().parents[1]/'.cache/models/demucs'


def digest_file(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            result.update(block)
    return result.hexdigest()


@lru_cache(maxsize=8)
def _check_file(path, size, mtime, inode):
    if size != EXPECTED_SIZE:
        return False, f'Checkpoint is incomplete or invalid: expected {EXPECTED_SIZE:,} bytes, got {size:,}. Git LFS pointers are not model weights.'
    if digest_file(path) != EXPECTED_SHA256:
        return False, 'Checkpoint SHA-256 does not match the pinned official six-source model.'
    return True, 'Checkpoint size and full SHA-256 verified.'


def checkpoint_status(repo=None):
    repo = repo or model_repo()
    path = repo/CHECKPOINT
    try:
        stat = path.stat()
    except FileNotFoundError:
        return False, 'The six-source checkpoint has not been installed.'
    good, detail = _check_file(str(path.resolve()), stat.st_size, stat.st_mtime_ns, stat.st_ino)
    if not good:
        return good, detail
    try:
        # Do not allow an arbitrary YAML bag to change model signatures/weights.
        if (repo/(MODEL_NAME+'.yaml')).read_text().strip() != BAG_CONTENT.strip():
            return False, 'Six-source model definition is missing or incorrect; run the installer.'
    except FileNotFoundError:
        return False, 'Six-source model definition is missing; run the installer.'
    return True, detail


def install_stream(stream, repo=None):
    """Atomic bounded copy + integrity check; no deserialization or code execution."""
    repo = repo or model_repo()
    repo.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.checkpoint-', suffix='.part', dir=repo)
    temp = Path(name)
    try:
        total = 0
        digest = hashlib.sha256()
        with os.fdopen(fd, 'wb') as out:
            while block := stream.read(min(1024*1024, EXPECTED_SIZE-total+1)):
                total += len(block)
                if total > EXPECTED_SIZE:
                    raise InvalidCheckpoint('Checkpoint exceeds the size of the approved model.')
                out.write(block)
                digest.update(block)
            out.flush()
            os.fsync(out.fileno())
        if total != EXPECTED_SIZE:
            raise InvalidCheckpoint(f'Expected the {EXPECTED_SIZE:,}-byte checkpoint; received {total:,} bytes. A Git LFS pointer or HTML download page is not usable.')
        if digest.hexdigest() != EXPECTED_SHA256:
            raise InvalidCheckpoint('Full SHA-256 verification failed. Existing model was not changed.')
        os.replace(temp, repo/CHECKPOINT)
        # Install a fixed bag definition, not YAML supplied by the uploader.
        atomic_text(repo/(MODEL_NAME+'.yaml'), BAG_CONTENT)
        atomic_text(repo/'provisioning.json', json.dumps({
            'model': MODEL_NAME, 'checkpoint': CHECKPOINT, 'sha256': EXPECTED_SHA256,
            'bytes': EXPECTED_SIZE, 'source': DOWNLOAD_URL,
        }, indent=2)+'\n')
        _check_file.cache_clear()
        return {'model': MODEL_NAME, 'sha256': EXPECTED_SHA256, 'bytes': total}
    finally:
        temp.unlink(missing_ok=True)


def atomic_text(path, content):
    fd, name = tempfile.mkstemp(prefix='.metadata-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as out:
            out.write(content)
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description='Install the pinned guitar-capable Demucs model with full SHA-256 verification.')
    parser.add_argument('--checkpoint', type=Path, help='Install an already downloaded checkpoint (no network needed).')
    parser.add_argument('--repo', type=Path, help='Override FRETWORK_DEMUCS_REPO or the local .cache model directory.')
    parser.add_argument('--check', action='store_true', help='Only check the existing model; never download or load it.')
    args = parser.parse_args()
    if args.check:
        good, detail = checkpoint_status(args.repo)
        print(detail)
        return 0 if good else 1
    try:
        if args.checkpoint:
            with args.checkpoint.open('rb') as stream:
                result = install_stream(stream, args.repo)
        else:
            print(f'Downloading {DOWNLOAD_URL}', flush=True)
            request = urllib.request.Request(DOWNLOAD_URL, headers={'User-Agent': 'Fretwork-model-installer/0.2'})
            with urllib.request.urlopen(request, timeout=60) as stream:
                result = install_stream(stream, args.repo)
        print(json.dumps(result, indent=2))
        print('Verified checkpoint installed. Restart is not needed for the running server to discover it.')
        return 0
    except (OSError, urllib.error.URLError, InvalidCheckpoint) as exc:
        print(f'Model installation did not complete: {exc}')
        print('If your server cannot reach the download host, download the checkpoint in your browser, then use --checkpoint PATH or the operator-enabled studio installer.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
