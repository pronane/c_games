"""Real inference only; development regression and independent event evaluation are separate."""
import argparse
from collections import Counter, defaultdict
import importlib.metadata
import json
import os
from pathlib import Path
import statistics
import subprocess
import tempfile
import time

from .core import audit, event_metrics, sha, PROTOCOL


def provenance(backend):
    from server.models import transcription_path
    model_path = transcription_path() if backend == 'basic_pitch' else None
    packages = {}
    for package in ('basic-pitch', 'onnxruntime', 'numpy', 'librosa', 'mir-eval', 'torch'):
        try: packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError: pass
    return {'backend_requested': backend, 'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
            'packages': packages, 'model_sha256': sha(model_path.read_bytes()) if model_path and model_path.is_file() else None,
            'model_hash_scope': 'Basic Pitch ONNX only; other backends must supply their own model provenance before external publication',
            'environment_flags': {k: os.environ[k] for k in ('FRETWORK_TRANSCRIBER','FRETWORK_DEVICE','FRETWORK_RILEY_LEVEL_GUARD','FRETWORK_DURATION_REVIEW','FRETWORK_REFINE','FRETWORK_LR_TRANSCRIBE') if k in os.environ},
            'code_sha256': {name: sha(Path(name).read_bytes()) for name in ('server/models.py','server/compare.py','server/transcription_check.py','benchmarks/practice_feedback/core.py','benchmarks/practice_feedback/__main__.py','benchmarks/practice_feedback/protocol.json')},
            'working_tree_dirty': bool(subprocess.check_output(['git','status','--porcelain'], text=True).strip())}


def infer(path, target, backend):
    from server.compare import transcribe_take_heard, compare_take
    from server.transcribers import transcription_label
    notes, heard = transcribe_take_heard(path, backend=backend)
    comparison = compare_take(notes, [target], transcription=transcription_label(backend), heard=heard)
    return notes, comparison['reports'][0], heard is not None


def regression(backend):
    """No synthesized audio, altered references or cached predictions. NOT independent holdout."""
    from benchmarks.regression.metrics import score_notes
    from server import transcription_check as tc
    import soundfile as sf
    root = Path(__file__).resolve().parents[1] / 'regression' / 'data' / 'guitarset'
    rows = []
    for annotation in sorted(root.glob('*.notes.json')):
        truth = json.loads(annotation.read_text()); path = root / truth['file']
        started = time.monotonic()
        notes, report, heard = infer(path, {'source': 'file', 'label': path.stem, 'notes': truth['notes'], 'bpm': truth['tempo']}, backend)
        y, sr = sf.read(path, dtype='float32'); check, _ = tc.check(y, sr, truth['notes'])
        counts = dict(Counter(n['kind'] for n in report['notes']))
        rows.append({'clip': path.name, 'performer_id': 'guitarset-player-05', 'source_id': path.stem, 'part': 'rhythm' if '_comp' in path.stem else 'lead',
                     'audio_sha256': sha(path.read_bytes()), 'annotation_sha256': sha(annotation.read_bytes()), 'seconds': len(y)/sr,
                     'note_metrics': score_notes(notes, truth['notes']), 'comparison_counts': counts,
                     'annotation_consistency_flags_per_100_notes': 100 * sum(v for k,v in counts.items() if k not in ('correct','uncertain')) / len(truth['notes']),
                     'uncertain_findings': counts.get('uncertain', 0), 'heard_map_used': heard,
                     'transcription_selfcheck_flagged_share_on_true_notes': check['summary']['flagged_share'],
                     'wall_seconds': time.monotonic()-started})
    if len(rows) != 3: raise RuntimeError('Expected all three bundled real recordings; incomplete regression is not a pass')
    return {'schema': 'practice-real-regression-v1', 'status': 'measured', 'inference_run': True, 'mocked': False, 'independent_holdout': False,
            'limitations': 'Previously used development clips; one performer, acoustic microphone only. Dataset notes are transcription references, not human playing-fault labels. Self-check uses true note playback vs real audio, not an independent correctness certificate.',
            'rows': rows, 'macro_note_f1': statistics.mean(r['note_metrics']['note_f1'] for r in rows), 'independent_performers': 1, 'quality_approved': False}


def evaluate(records, backend):
    rows = []
    with tempfile.TemporaryDirectory(prefix='practice-feedback-') as tmp:
        for i, record in enumerate(records):
            path = Path(tmp) / f'{i}.wav'; path.write_bytes(record['audio'])
            _, report, heard = infer(path, {'source': 'file', 'label': 'Audited reference', 'notes': record['notes'], 'bpm': record['bpm']}, backend)
            metrics = event_metrics(report['notes'], record['labels'], PROTOCOL['event_tolerance_seconds'])
            rows.append({k: v for k,v in record.items() if k not in ('audio','notes','labels') } | {'metrics': metrics, 'heard_map_used': heard, 'alignment_warning': report.get('alignment_warning')})
    # Each record is already a distinct physical performance; macro means do not weight dense clips more.
    def summary(selected):
        kinds = {}
        for kind in ('pitch','timing','missing','extra','sustain'):
            counts = {key: sum(r['metrics']['by_kind'][kind][key] for r in selected) for key in ('tp','fp','fn')}
            tp, fp, fn = counts['tp'], counts['fp'], counts['fn']
            kinds[kind] = counts | {'precision': tp/(tp+fp) if tp+fp else None, 'recall': tp/(tp+fn) if tp+fn else None, 'f1': 2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None}
        return {'sources': len(selected), 'by_kind_micro': kinds, 'source_macro_false_warnings_per_correct_minute': statistics.mean(values) if (values := [r['metrics']['false_warnings_per_correct_minute'] for r in selected if r['metrics']['false_warnings_per_correct_minute'] is not None]) else None,
                'alignment_warning_sources': sum(bool(r['alignment_warning']) for r in selected)}
    groups = {f'{condition}/{part}': summary([r for r in rows if r['condition']==condition and r['part']==part]) for condition in sorted({r['condition'] for r in rows}) for part in sorted({r['part'] for r in rows})}
    return {'schema': 'practice-feedback-measurement-v1', 'status': 'measured', 'inference_run': True, 'mocked': False, 'rows': rows, 'summary': summary(rows), 'groups': groups, 'quality_approved': False,
            'limitations': 'Localized issue types/times, not exact pitch diagnosis; declaration-based independence, model-training overlap unknown. No threshold tuning, policy promotion or bootstrap confidence claim.'}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('audit','evaluate','regression')); p.add_argument('--manifest', type=Path, default=Path(__file__).with_name('intake.json'))
    p.add_argument('--backend', choices=('basic_pitch','riley','gaps'), default='basic_pitch'); p.add_argument('--out', required=True, type=Path)
    args = p.parse_args(argv); result = {'inference_run': False, 'inference_attempted': False, 'inference_completed': False, 'quality_approved': False}; code = 0
    try:
        if args.action == 'regression':
            result['inference_attempted'] = True; result.update(regression(args.backend)); result['provenance'] = provenance(args.backend); result['inference_completed'] = True
        else:
            result, records = audit(args.manifest)
            result.update(inference_attempted=False, inference_completed=False)
            if result['reasons']: code = 3
            elif args.action == 'evaluate':
                result['inference_attempted'] = True
                result.update(evaluate(records, args.backend)); result['provenance'] = provenance(args.backend); result['inference_completed'] = True
    except Exception as exc:
        # Never leave a previous successful report in place after a failed run.
        result.update(status='error', error=f'{type(exc).__name__}: {exc}', inference_run=None if result.get('inference_attempted') else False, inference_completed=False); code = 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'status': result['status'], 'inference_run': result['inference_run'], 'out': str(args.out)}))
    return code


if __name__ == '__main__': raise SystemExit(main())
