#!/usr/bin/env python3
"""Retrieve bounded low-resolution motion previews through GitHub's API."""
import argparse
import base64
import hashlib
import json
import re
from pathlib import Path
from download_review_frames import gh_json


def save_preview(check, run_id, output):
    data = json.loads(check['output']['text'])
    label = data.get('label', '')
    if data.get('format') != 1 or data.get('run_id') != str(run_id) or not re.fullmatch(r'[a-z0-9-]{1,48}', label):
        raise ValueError('invalid preview metadata')
    encoded = data.get('mp4_base64')
    if not isinstance(encoded, str) or len(encoded) > 60000: raise ValueError('invalid preview size')
    raw = base64.b64decode(encoded, validate=True)
    if len(raw) < 12 or raw[4:8] != b'ftyp' or hashlib.sha256(raw).hexdigest() != data.get('sha256'):
        raise ValueError('invalid preview data')
    output.mkdir(parents=True, exist_ok=True)
    path = output / (label + '.mp4'); path.write_bytes(raw)
    return path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('run_id'); p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    if not a.run_id.isdigit(): p.error('run ID must be numeric')
    repo = gh_json('repo', 'view', '--json', 'nameWithOwner')['nameWithOwner']
    sha = gh_json('run', 'view', a.run_id, '--json', 'headSha')['headSha']
    found = []
    for page in range(1, 11):
        checks = gh_json('api', f'repos/{repo}/commits/{sha}/check-runs?per_page=100&page={page}')['check_runs']
        for check in checks:
            if check.get('external_id') == a.run_id and check.get('name', '').startswith('Motion review preview: '):
                found.append(save_preview(check, a.run_id, a.out))
        if len(checks) < 100: break
    if not found: raise SystemExit('No API-accessible previews found for this workflow run.')
    for path in found: print(path)

if __name__ == '__main__': main()
