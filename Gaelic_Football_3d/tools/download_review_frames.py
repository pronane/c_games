#!/usr/bin/env python3
"""Fetch machine-readable stills from a workflow's GitHub check runs.

Requires gh authentication and access to api.github.com. The result is a small
set of sampled images, not the full workflow video artifact.
"""
import argparse
import base64
import json
import re
import subprocess
from pathlib import Path


def gh_json(*args):
    return json.loads(subprocess.run(['gh', *args], check=True, stdout=subprocess.PIPE, text=True).stdout)


def save_frames(check, run_id, output):
    data = json.loads(check['output']['text'])
    label = data.get('label', '')
    if data.get('format') != 1 or data.get('run_id') != str(run_id) or not re.fullmatch(r'[a-z0-9-]{1,48}', label):
        raise ValueError('invalid review frame metadata')
    frames = data.get('frames')
    if not isinstance(frames, list) or not 1 <= len(frames) <= 12: raise ValueError('invalid frame count')
    folder = output / label; folder.mkdir(parents=True, exist_ok=True)
    for i, frame in enumerate(frames):
        raw = base64.b64decode(frame['jpeg_base64'], validate=True)
        if len(raw) > 100000 or not raw.startswith(b'\xff\xd8') or not raw.endswith(b'\xff\xd9'):
            raise ValueError('invalid JPEG frame')
        (folder / f'frame-{i+1:02}.jpg').write_bytes(raw)
    return label, len(frames)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_id'); parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not args.run_id.isdigit(): parser.error('run ID must be numeric')
    repo = gh_json('repo', 'view', '--json', 'nameWithOwner')['nameWithOwner']
    run = gh_json('run', 'view', args.run_id, '--json', 'headSha')
    sha = run['headSha']; found = []
    for page in range(1, 11):
        response = gh_json('api', f'repos/{repo}/commits/{sha}/check-runs?per_page=100&page={page}')
        checks = response['check_runs']
        for check in checks:
            if check.get('external_id') == args.run_id and check.get('name', '').startswith('Motion review frames: '):
                found.append(save_frames(check, args.run_id, args.out))
        if len(checks) < 100: break
    if not found: raise SystemExit('No API-accessible review frames found for this workflow run.')
    for label, count in found: print(f'{label}: {count} frames -> {args.out / label}')


if __name__ == '__main__': main()
