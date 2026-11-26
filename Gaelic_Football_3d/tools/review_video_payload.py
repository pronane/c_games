#!/usr/bin/env python3
"""Create a small, short MP4 preview in GitHub check output, not a full artifact."""
import argparse
import base64
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

MAX_TEXT = 60000


def build_payload(video, label, sha, run_id, repository, ffmpeg='ffmpeg', hand_crop=False, foot_detail=False):
    if not re.fullmatch(r'[a-z0-9-]{1,48}', label): raise ValueError('invalid label')
    if not re.fullmatch(r'[0-9a-f]{40}', sha) or not str(run_id).isdigit(): raise ValueError('invalid workflow identity')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', repository): raise ValueError('invalid repository')
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / 'preview.mp4'
        if hand_crop and foot_detail: raise ValueError('crop modes are mutually exclusive')
        start, duration, fps = (4.5, 1.8, 15) if foot_detail else (4, 3, 12)
        settings = ((480, 32), (400, 35), (320, 38), (256, 41)) if foot_detail else ((320, 35), (256, 38), (192, 41))
        for width, crf in settings:
            filt = (f'crop=500:360:280:70,scale={width}:-2,fps={fps}' if hand_crop else f'scale={width}:-2,fps={fps}')
            subprocess.run([ffmpeg, '-v', 'error', '-ss', str(start), '-i', str(video), '-t', str(duration), '-vf', filt,
                            '-an', '-c:v', 'libx264', '-preset', 'veryslow', '-crf', str(crf),
                            '-movflags', '+faststart', '-y', str(out)], check=True)
            data = out.read_bytes()
            if len(data) < 12 or data[4:8] != b'ftyp': raise ValueError('invalid MP4 preview')
            text = json.dumps({'format': 1, 'run_id': str(run_id), 'label': label, 'start': start,
                               'duration': duration, 'fps': fps, 'width': width, 'hand_crop': hand_crop,
                               'sha256': hashlib.sha256(data).hexdigest(),
                               'mp4_base64': base64.b64encode(data).decode('ascii')}, separators=(',', ':'))
            if len(text) <= MAX_TEXT:
                return {'name': f'Motion review preview: {label}', 'head_sha': sha,
                        'external_id': str(run_id), 'status': 'completed', 'conclusion': 'neutral',
                        'details_url': f'https://github.com/{repository}/actions/runs/{run_id}',
                        'output': {'title': f'Low-resolution motion preview: {label}',
                                   'summary': f'{duration} seconds at {fps} fps; compressed preview only. Full video remains in the artifact.', 'text': text}}
    raise ValueError('preview exceeds check output size limit')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('video', type=Path); p.add_argument('--label', required=True)
    p.add_argument('--sha', required=True); p.add_argument('--run-id', required=True)
    p.add_argument('--repository', required=True); p.add_argument('--ffmpeg', default='ffmpeg')
    p.add_argument('--hand-crop', action='store_true')
    p.add_argument('--foot-detail', action='store_true', help='shorter, higher-resolution fixed-camera pass')
    a = p.parse_args()
    print(json.dumps(build_payload(a.video, a.label, a.sha, a.run_id, a.repository, a.ffmpeg, a.hand_crop, a.foot_detail)))

if __name__ == '__main__': main()
