#!/usr/bin/env python3
"""Scripted presentation guards and fingertip correction transitions, not gameplay."""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(root/'tools'))
from inspect_shorts_skin import load_glb
from inspect_hand_mesh import measure

if len(sys.argv) not in (3,4): raise SystemExit('usage: hand_transition_tests.py TOOL MODEL [--surface]')
tool, model = (str(Path(x).resolve()) for x in sys.argv[1:3])
surface=len(sys.argv)==4 and sys.argv[3]=='--surface'
with tempfile.TemporaryDirectory() as tmp:
    for fps in (30,60):
        out=Path(tmp)/f'{fps}.json'
        proc=subprocess.run([tool,'--export-hand-transition',model,str(out),str(fps)],check=True,capture_output=True,text=True)
        lines=[line for line in proc.stdout.splitlines() if line.startswith('hand_transition ')]
        assert len(lines)==12
        print('\n'.join(lines))
        data=json.loads(out.read_text()); assert data['scenario']=='scripted-hand-transition' and len(data['frames'])==12
        for frame in data['frames']:
            if frame['state'] in ('carry','jump','handpass','solo'):
                assert frame['raw']==frame['adjusted'],frame['state']
        for name in ('carry','jump','handpass','solo'):
            line=next(x for x in lines if f'state={name} ' in x)
            assert f'guarded_noops={fps} ' in line and re.search(r'boundary_delta_deg=[0-9.]+',line)
        if surface and fps==30:
            doc,blob=load_glb(model); report=measure(doc,blob,data,surface=True)
            assert report['surface_samples']==12 and len(report['sampled_surface_by_state'])==12
            for frame in report['sampled_surface_by_state']:
                if frame['state'] in ('carry','jump','handpass','solo'):
                    for side in frame['sides'].values(): assert side['raw']==side['adjusted']
            print('hand_transition_surfaces '+json.dumps(report['sampled_surface_by_state'],separators=(',',':')))
print('scripted hand transition tests passed (no live gameplay or rendered validation)')
