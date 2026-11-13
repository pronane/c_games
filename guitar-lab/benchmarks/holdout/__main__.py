"""Audit or evaluate independent, human-labelled guitar holdouts. Never promotes defaults."""
import argparse
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import subprocess
import sys

from .core import audit, sha256, PROTOCOL


def evaluate(records):
    import numpy as np
    import mir_eval
    from server.models import transcribe
    from server.compare import _duration_off
    from benchmarks.regression.metrics import score_notes
    rows=[]
    previous=os.environ.get('FRETWORK_RILEY_LEVEL_GUARD')
    try:
        for record in records:
            ref=record['notes']; by_id={n['id']:i for i,n in enumerate(ref)}
            for policy,flag in [('baseline','0'),('guard','1')]:
                os.environ['FRETWORK_RILEY_LEVEL_GUARD']=flag
                # No condition or label is passed into inference.
                est=transcribe(record['audio_path'],backend='riley',midi_min=40,midi_max=88)
                intervals=lambda ns: np.array([[n['time'],n['time']+max(n['duration'],.01)] for n in ns])
                hz=lambda ns: np.array([440*2**((n['midi']-69)/12) for n in ns])
                pairs=mir_eval.transcription.match_notes(intervals(ref),hz(ref),intervals(est),hz(est),offset_ratio=None) if est else []
                matched=dict(pairs); offsets=[];counts=Counter()
                for i,j in pairs:
                    offsets.append(abs(ref[i]['time']+ref[i]['duration']-est[j]['time']-est[j]['duration']))
                for example in record['sustain']:
                    index=by_id[example['note_id']];truth=example['judgement']
                    counts[truth+'_total']+=1
                    if index not in matched:
                        counts[truth+'_unmatched']+=1
                        continue
                    predicted=est[matched[index]]
                    flagged=_duration_off(predicted['duration'],example['expected_duration'],1)
                    counts[truth+'_matched']+=1
                    counts[truth+('_flagged' if flagged else '_not_flagged')]+=1
                rows.append({'clip':record['id'],'source_id':record['source_id'],'performer_id':record['performer_id'],
                             'condition':record['condition'],'capture':record['capture'],'policy':policy,
                             'audio_sha256':record['audio_sha256'],'labels_sha256':record['labels_sha256'],
                             **score_notes(est,ref),'matched_median_abs_offset_error_s':float(np.median(offsets)) if offsets else None,
                             'offset_pair_count':len(offsets),'raw_sustain_counts':dict(counts)})
    finally:
        if previous is None:os.environ.pop('FRETWORK_RILEY_LEVEL_GUARD',None)
        else:os.environ['FRETWORK_RILEY_LEVEL_GUARD']=previous
    # Pair by clip, then average within source before bootstrap: variants are not independent.
    grouped=defaultdict(list)
    for clip in {r['clip'] for r in rows}:
        pair={r['policy']:r for r in rows if r['clip']==clip}
        if pair['baseline']['capture']=='real':
            grouped[pair['baseline']['source_id']].append(pair['guard']['note_f1']-pair['baseline']['note_f1'])
    deltas=[float(np.mean(v)) for v in grouped.values()]
    ci=None
    if len(deltas)>=2:
        rng=np.random.default_rng(20261031)
        samples=np.mean(rng.choice(deltas,size=(5000,len(deltas)),replace=True),axis=1)
        ci=[float(x) for x in np.quantile(samples,[.025,.975])]
    summaries=[]
    for condition in sorted({r['condition'] for r in rows}):
        for policy in ('baseline','guard'):
            selected=[r for r in rows if r['condition']==condition and r['policy']==policy and r['capture']=='real']
            source_values=defaultdict(list);counts=Counter()
            for row in selected:
                source_values[row['source_id']].append(row['note_f1']);counts.update(row['raw_sustain_counts'])
            rate=lambda a,b: counts[a]/counts[b] if counts[b] else None
            summaries.append({'condition':condition,'policy':policy,'independent_sources':len(source_values),
                              'source_macro_note_f1':float(np.mean([np.mean(v) for v in source_values.values()])) if source_values else None,
                              'raw_sustain_counts':dict(counts),
                              'correct_false_warning_rate_among_matched':rate('correct_flagged','correct_matched'),
                              'correct_unmatched_rate':rate('correct_unmatched','correct_total'),
                              'short_error_detection_rate_all_examples':rate('too_short_flagged','too_short_total'),
                              'long_error_detection_rate_all_examples':rate('too_long_flagged','too_long_total')})
    return {'rows':rows,'condition_summaries':summaries,'paired_source_mean_note_f1_delta':float(np.mean(deltas)) if deltas else None,
            'source_bootstrap_95_percent_interval':ci,'independent_bootstrap_units':len(deltas),
            'quality_approved':False,
            'sustain_interpretation':'Report false warnings on correct notes, short/long error misses, and unmatched coverage separately. Review wording is not an estimator improvement.'}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['audit','evaluate'])
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args(argv)
    try:
        report,records=audit(args.manifest)
        if args.action=='evaluate' and report['missing']:
            report['inference_run']=False
        elif args.action=='evaluate':
            report.update(evaluate(records));report['inference_run']=True
            report['policy_code_sha256']=sha256(Path(__file__).resolve().parents[2]/'server'/'evidence_policy.py')
            report['source_commit']=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
            checkpoint=os.getenv('FRETWORK_RILEY_CHECKPOINT')
            report['checkpoint_sha256']=sha256(checkpoint) if checkpoint else None
            import importlib.metadata
            report['versions']={name:importlib.metadata.version(name) for name in ('torch','torchlibrosa','numpy','librosa','mir_eval')}
    except (ValueError,OSError,KeyError,TypeError,AttributeError) as exc:
        report={'status':'invalid_intake','error':str(exc),'inference_run':False}
    except Exception as exc:
        report={'status':'evaluation_error','error':f'{type(exc).__name__}: {exc}','quality_approved':False}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2)+'\n')
    print(report['status'])
    if report['status'] in ('invalid_intake','evaluation_error'):return 1
    return 3 if report.get('missing') else 0


if __name__=='__main__':sys.exit(main())
