#!/usr/bin/env python3
"""Exercise frame encoding/decoding without network or video dependencies."""
import base64
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'tools'))
import review_frame_payload as pack
import download_review_frames as unpack

class Result:
    stdout = b'\xff\xd8test\xff\xd9'

with tempfile.TemporaryDirectory() as tmp:
    with patch.object(pack.subprocess, 'run', return_value=Result()):
        payload = pack.build_payload('sample.mp4', 'hands-before', 'a'*40, '123', 'owner/repo')
    assert payload['external_id'] == '123' and payload['conclusion'] == 'neutral'
    with patch.object(pack.subprocess, 'run', return_value=Result()) as run:
        cropped = pack.build_payload('sample.mp4', 'hands-before', 'a'*40, '123', 'owner/repo', hand_crop=True)
    assert json.loads(cropped['output']['text'])['hand_crop']
    assert 'crop=500:360:280:70' in run.call_args.args[0][run.call_args.args[0].index('-vf')+1]
    label, count = unpack.save_frames({'output': payload['output']}, '123', Path(tmp))
    assert label == 'hands-before' and count == len(pack.TIMES)
    assert (Path(tmp) / label / 'frame-01.jpg').read_bytes() == Result.stdout
    data = json.loads(payload['output']['text'])
    data['label'] = '../escape'
    try: unpack.save_frames({'output': {'text': json.dumps(data)}}, '123', Path(tmp))
    except ValueError: pass
    else: raise AssertionError('unsafe label accepted')
    try: pack.build_payload('x', '../escape', 'a'*40, '123', 'owner/repo')
    except ValueError: pass
    else: raise AssertionError('unsafe check label accepted')
print('review frame payload tests passed')
