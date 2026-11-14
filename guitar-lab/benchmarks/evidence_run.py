"""Paired, opt-in evidence policies on labelled public audio and an optional unlabelled take.

Run from guitar-lab: python -m benchmarks.evidence_run --out benchmarks/evidence/audio.json
Optional --take /local/file.wav is NEVER accuracy-labelled or copied into output.
"""
import argparse
from collections import Counter
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

import numpy as np
import soundfile as sf
from scipy.signal import fftconvolve

from benchmarks.regression.catalog import GUITARSET, GUITARSET_CLIPS, guitarset_notes
from benchmarks.regression.metrics import score_notes
from server.models import transcribe
from server.evidence_policy import guarded_level
from server.compare import compare_take


def conditions(y,sr):
    rng=np.random.default_rng(20261031)
    t=np.arange(sr*2)/sr
    ir=rng.normal(size=len(t))*np.exp(-np.log(1000)*t/2)
    ir*=.6/max(np.linalg.norm(ir),1e-12);ir[0]+=1
    room=fftconvolve(y,ir)[:len(y)]
    room*=np.sqrt(np.mean(y**2))/max(np.sqrt(np.mean(room**2)),1e-12)
    return {'original':y,'quiet_minus24db':y*10**(-24/20),
            'hard_clipped':np.clip(y*8,-.3,.3),'synthetic_room_rt60_2s':room}


def paired(path, ref=None):
    rows=[]
    for policy in ('baseline','experimental'):
        os.environ['FRETWORK_RILEY_LEVEL_GUARD']='1' if policy=='experimental' else '0'
        os.environ['FRETWORK_DURATION_REVIEW']='1' if policy=='experimental' else '0'
        start=time.monotonic();notes=transcribe(path,backend='riley');elapsed=time.monotonic()-start
        row={'policy':policy,'runtime_seconds':elapsed,'n_est':len(notes)}
        if ref is not None:
            report=compare_take(notes,[{'source':'file','notes':ref}],transcription='clean-guitar Riley')['reports'][0]
            row.update(score_notes(notes,ref),feedback_counts=dict(Counter(n['kind'] for n in report['notes'])),
                       duration_policy=report.get('duration_policy','legacy'),
                       duration_review_messages=sum('review by ear' in n['message'] for n in report['notes']),
                       correct_reference_fraction=sum(n['kind']=='correct' for n in report['notes'])/max(len(ref),1))
        else:
            row['accuracy']=None
            row['limitation']='Unlabelled user audio: note counts and model agreement are NOT accuracy.'
        rows.append(row)
    return rows


def run(take=None):
    results=[];private=[]
    with tempfile.TemporaryDirectory(prefix='guitar-evidence-') as tmp:
        for clip in GUITARSET_CLIPS:
            y,sr=sf.read(GUITARSET/clip['wav'],dtype='float32');y=y[:sr*8]
            if y.ndim==2:y=y.mean(axis=1)
            ref=[dict(n,duration=min(n['duration'],8-n['time'])) for n in guitarset_notes(GUITARSET/clip['notes']) if n['time']<8]
            for condition,audio in conditions(y,sr).items():
                path=Path(tmp)/'public.wav';sf.write(path,audio,sr,subtype='FLOAT')
                for row in paired(path,ref):results.append(dict(row,clip=clip['id'],condition=condition))
                print(clip['id'],condition,'done',flush=True)
        if take:
            y,sr=sf.read(take,dtype='float32')
            if y.ndim==2:y=y.mean(axis=1)
            for start in (0,145,290):
                audio=y[start*sr:(start+10)*sr]
                if len(audio)<sr:continue
                path=Path(tmp)/'private.wav';sf.write(path,audio,sr,subtype='FLOAT')
                for row in paired(path):private.append(dict(row,start_s=start,duration_s=len(audio)/sr))
                print('private window',start,'done',flush=True)
    return {'seed':20261031,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'working_diff_sha256':hashlib.sha256(subprocess.check_output(['git','diff','HEAD'])).hexdigest(),
            'versions':{p:importlib.metadata.version(p) for p in ('torch','torchlibrosa','numpy','numba','librosa','basic-pitch','onnxruntime','mir_eval')},
            'limitations':['Three public source performances, one player; correlated synthetic variants, eight-second windows.',
                           'Experimental policy evaluated on reused regression data; not held-out release validation.',
                           'Duration review changes wording only; diagnostic counts/scores intentionally unchanged.',
                           'Private take is unlabelled and only fixed ten-second windows are transcribed.',
                           'No real full-band separation, real amp library, GPU or physical USB test.'],
            'public_rows':results,'private_rows':private,
            'private_wav_sha256':hashlib.sha256(Path(take).read_bytes()).hexdigest() if take else None}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);p.add_argument('--take',type=Path)
    args=p.parse_args();payload=run(args.take);args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(payload,indent=2)+'\n')


if __name__=='__main__':main()
