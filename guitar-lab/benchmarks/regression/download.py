"""Download EGSet12 and the Guitar-TECHS musical excerpts.

Official Zenodo files only. Audio and tabs land in ``data/private/`` (gitignored).
The committed manifest holds the checksums.

From ``guitar-lab/``::

    python -m benchmarks.regression.download
    python -m benchmarks.regression.download --align
    python -m benchmarks.regression.download --check

``--check`` exits 0 when the files match the manifest, and 3 when they are
absent. A checksum mismatch exits 1. EGDB, GOAT, Cambridge-MT, and the rest
of Guitar-TECHS are not fetched.
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from benchmarks.regression import catalog
from benchmarks.regression.electric import (
    MANIFEST, load_manifest, md5_file, sha256_file,
)

UA = 'c_games-guitar-lab-regression/1.0'
# Room-mic mp3s live in the same zip. They are not the scored reference.
_EXTRACT_PREFIXES = (
    'P3_music/audio/micamp/',
    'P3_music/audio/directinput/',
    'P3_music/midi/',
)


def official_url(record: str, name: str) -> str:
    """Official file bytes for a Zenodo record.

    The record page is ``https://zenodo.org/records/{record}``. The content
    link is the file URL that record publishes (``links.self`` in the API).
    """
    return f'https://zenodo.org/api/records/{record}/files/{urllib.parse.quote(name)}/content'


def planned_downloads():
    """``(dataset, filename, url, md5, size)`` for every official file this gate fetches."""
    manifest = load_manifest()
    eg = manifest['egset12']
    rows = []
    for name, item in eg['files'].items():
        rows.append(('egset12', name, official_url(eg['record'], name), item['md5'], int(item['size'])))
    archive = manifest['guitar_techs']['archive']
    te = manifest['guitar_techs']
    rows.append(('guitar_techs', archive['name'], official_url(te['record'], archive['name']),
                 archive['md5'], int(archive['size'])))
    return rows


def _dest(dataset: str, name: str) -> Path:
    if dataset == 'egset12':
        return catalog.egset12_dir() / name
    return catalog.PRIVATE / 'cache' / name


def _download(url: str, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + '.part')
    request = urllib.request.Request(url, headers={'User-Agent': UA})
    delay = 4
    last = None
    for _attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=180) as response, tmp.open('wb') as out:
                shutil.copyfileobj(response, out, length=1024 * 1024)
            tmp.replace(dest)
            return
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            tmp.unlink(missing_ok=True)
            time.sleep(delay)
            delay *= 2
    raise SystemExit(f'download failed for {url}: {last}')


def _matches(path: Path, md5: str, size: int) -> bool:
    if not path.is_file():
        return False
    if path.stat().st_size != size:
        return False
    return md5_file(path) == md5


def fetch(datasets=('egset12', 'guitar_techs')):
    wanted = set(datasets)
    got = []
    for dataset, name, url, md5, size in planned_downloads():
        if dataset not in wanted:
            continue
        dest = _dest(dataset, name)
        if _matches(dest, md5, size):
            print(f'ok {dest.relative_to(catalog.DATA)}')
            got.append(dest)
            continue
        print(f'download {url}')
        _download(url, dest)
        if not _matches(dest, md5, size):
            raise SystemExit(f'checksum mismatch for {name}: expected md5 {md5} size {size}')
        print(f'ok {dest.relative_to(catalog.DATA)}')
        got.append(dest)
    if 'guitar_techs' in wanted:
        extract_techs()
    return got


def _safe_members(zf: zipfile.ZipFile):
    for info in zf.infolist():
        name = info.filename
        parts = Path(name).parts
        if name.startswith('/') or '..' in parts or name.startswith('__MACOSX'):
            continue
        if not any(name.startswith(prefix) for prefix in _EXTRACT_PREFIXES):
            continue
        if name.endswith('/'):
            continue
        if not name.lower().endswith(('.wav', '.mid', '.midi')):
            continue
        yield info


def extract_techs():
    archive = load_manifest()['guitar_techs']['archive']
    zip_path = _dest('guitar_techs', archive['name'])
    if not _matches(zip_path, archive['md5'], int(archive['size'])):
        raise SystemExit(f'{archive["name"]} is missing or does not match the manifest')
    root = catalog.guitar_techs_dir()
    root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        members = list(_safe_members(zf))
        if len(members) < 36:
            raise SystemExit(f'{archive["name"]} did not contain the 12 excerpts (mic, DI, MIDI)')
        zf.extractall(root, members)
    print(f'extracted {len(members)} excerpt files into {root.relative_to(catalog.DATA)}')


def check(datasets=('egset12', 'guitar_techs')) -> int:
    """0 when present and valid, 3 when absent, 1 when corrupt."""
    wanted = set(datasets)
    missing = []
    bad = []
    for dataset, name, _url, md5, size in planned_downloads():
        if dataset not in wanted:
            continue
        dest = _dest(dataset, name)
        if not dest.is_file():
            missing.append(str(dest.relative_to(catalog.DATA)))
        elif not _matches(dest, md5, size):
            bad.append(name)
    if 'guitar_techs' in wanted and not missing and not bad:
        if not catalog.available_summary()['guitar_techs']:
            missing.append('guitar_techs excerpts (zip present, not extracted)')
    if bad:
        print('checksum mismatch: ' + ', '.join(bad))
        return 1
    if missing:
        print('not on disk:')
        for item in missing:
            print(f'  {item}')
        print('Download with: python -m benchmarks.regression.download')
        return 3
    print('electric datasets match the manifest')
    return 0


def record_hashes():
    """Fill sha256 fields in the manifest from the files on disk."""
    manifest = load_manifest()
    for name, item in manifest['egset12']['files'].items():
        path = catalog.egset12_dir() / name
        if not path.is_file():
            raise SystemExit(f'missing {path}')
        item['sha256'] = sha256_file(path)
    archive = manifest['guitar_techs']['archive']
    zip_path = _dest('guitar_techs', archive['name'])
    archive['sha256'] = sha256_file(zip_path)
    extracted = {}
    root = catalog.guitar_techs_dir()
    for path in sorted(root.rglob('*')):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {'.wav', '.mid', '.midi'}:
            continue
        rel = path.relative_to(root).as_posix()
        extracted[rel] = {'sha256': sha256_file(path), 'size': path.stat().st_size}
    if len(extracted) < 36:
        raise SystemExit('refusing to record hashes before the excerpts are extracted')
    manifest['guitar_techs']['extracted'] = extracted
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
    print(f'recorded sha256 for {len(manifest["egset12"]["files"])} EGSet12 files '
          f'and {len(extracted)} Guitar-TECHS files')


def main(argv=None):
    parser = argparse.ArgumentParser(description='Download EGSet12 and Guitar-TECHS musical excerpts')
    parser.add_argument('--dataset', choices=('all', 'egset12', 'guitar-techs'), default='all')
    parser.add_argument('--check', action='store_true', help='Verify files. Exit 3 if they are absent.')
    parser.add_argument('--align', action='store_true', help='Freeze pitch-blind onset lags. Does not transcribe.')
    parser.add_argument('--record-hashes', action='store_true', help='Write sha256 of the local files into the manifest.')
    args = parser.parse_args(argv)
    selected = ('egset12', 'guitar_techs') if args.dataset == 'all' else (
        ('guitar_techs',) if args.dataset == 'guitar-techs' else ('egset12',))
    if args.check:
        raise SystemExit(check(selected))
    fetch(selected)
    if args.record_hashes:
        record_hashes()
    if args.align:
        from benchmarks.regression.electric import freeze_alignment
        payload = freeze_alignment()
        print(payload['guitar_techs_signal_reason'])
        print(f'wrote {catalog.ROOT / "reference" / "electric_alignment.json"}')


if __name__ == '__main__':
    main()
