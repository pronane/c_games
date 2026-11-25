#!/usr/bin/env python3
"""Round-trip and reject malformed API motion previews without network or ffmpeg."""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import review_video_payload as pack
import download_review_videos as unpack

raw = b'\x00\x00\x00\x18ftypisomtest'
def fake_run(cmd, check):
    Path(cmd[-1]).write_bytes(raw)

with tempfile.TemporaryDirectory() as tmp, patch.object(pack.subprocess, 'run', side_effect=fake_run):
    p = pack.build_payload('test', 'hands-before', 'a'*40, '123', 'owner/repo', hand_crop=True)
    path = unpack.save_preview({'output': p['output']}, '123', Path(tmp))
    assert path.read_bytes() == raw
    data = json.loads(p['output']['text'])
    for change in ({'label': '../evil'}, {'sha256': '0'*64}, {'run_id': '124'}, {'mp4_base64': '!' }):
        bad = dict(data); bad.update(change)
        try: unpack.save_preview({'output': {'text': json.dumps(bad)}}, '123', Path(tmp))
        except ValueError: pass
        else: raise AssertionError(f'accepted invalid data: {change}')
    try: pack.build_payload('test', '../bad', 'a'*40, '123', 'owner/repo')
    except ValueError: pass
    else: raise AssertionError('accepted invalid label')
print('review video payload tests passed')
