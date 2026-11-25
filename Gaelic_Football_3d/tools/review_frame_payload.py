#!/usr/bin/env python3
"""Encode a small sample of a video into a GitHub check-run payload.

Full videos remain workflow artifacts. These downscaled stills are a fallback
for environments that can reach api.github.com but not the artifact host; they
are not a substitute for reviewing motion. Uses the system ffmpeg executable.
"""
import argparse
import base64
import json
import re
import subprocess
from pathlib import Path

TIMES = (4.2, 4.7, 5.2, 5.7, 6.2, 6.7)
MAX_TEXT = 60000  # GitHub's check output text limit is 65535 characters.


def build_payload(video, label, sha, run_id, repository, ffmpeg='ffmpeg'):
    if not re.fullmatch(r'[a-z0-9-]{1,48}', label):
        raise ValueError('invalid review label')
    if not re.fullmatch(r'[0-9a-f]{40}', sha) or not str(run_id).isdigit():
        raise ValueError('invalid workflow identity')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository):
        raise ValueError('invalid repository')
    for width, quality in ((400, 12), (320, 15), (256, 20), (192, 25)):
        frames = []
        for second in TIMES:
            image = subprocess.run([ffmpeg, '-v', 'error', '-ss', str(second), '-i', str(video),
                                    '-frames:v', '1', '-vf', f'scale={width}:-2', '-q:v', str(quality),
                                    '-f', 'image2pipe', '-vcodec', 'mjpeg', 'pipe:1'],
                                   check=True, stdout=subprocess.PIPE).stdout
            if not image.startswith(b'\xff\xd8') or not image.endswith(b'\xff\xd9'):
                raise ValueError(f'missing or invalid frame at {second}s')
            frames.append({'seconds': second, 'jpeg_base64': base64.b64encode(image).decode('ascii')})
        text = json.dumps({'format': 1, 'run_id': str(run_id), 'label': label,
                           'width': width, 'frames': frames}, separators=(',', ':'))
        if len(text) <= MAX_TEXT:
            return {'name': f'Motion review frames: {label}', 'head_sha': sha,
                    'external_id': str(run_id), 'status': 'completed', 'conclusion': 'neutral',
                    'details_url': f'https://github.com/{repository}/actions/runs/{run_id}',
                    'output': {'title': f'Sampled review frames: {label}',
                               'summary': 'Six downscaled stills for API-based review. Full video remains in the workflow artifact; stills do not validate motion.',
                               'text': text}}
    raise ValueError('review frames exceed the check output size limit')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('video', type=Path); parser.add_argument('--label', required=True)
    parser.add_argument('--sha', required=True); parser.add_argument('--run-id', required=True)
    parser.add_argument('--repository', required=True); parser.add_argument('--ffmpeg', default='ffmpeg')
    args = parser.parse_args()
    print(json.dumps(build_payload(args.video, args.label, args.sha, args.run_id, args.repository, args.ffmpeg)))


if __name__ == '__main__': main()
