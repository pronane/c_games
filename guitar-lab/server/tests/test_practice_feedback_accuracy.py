"""Metric/intake tests use synthetic fixtures. Opt-in API tests below run real audio/model."""
import base64
from contextlib import contextmanager
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import wave

import pytest

from benchmarks.practice_feedback.core import audit, event_metrics, js_json, packet, sha, cluster_findings

ROOT = Path(__file__).resolve().parents[2]


def bundle(index=0):
    audio = io.BytesIO()
    with wave.open(audio, 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(8000); f.writeframes(bytes([index+1, 0])*280000)
    p = {'schema': 'fretwork-listening-packet-v1', 'id': f'packet-{index}', 'window': {'start': 0, 'end': 35, 'speed': 1}, 'reference': {'notes': [{'time': 1, 'duration': .5, 'midi': 64}], 'bpm': 120, 'tuning': 'standard', 'part': 'guitar', 'revision': 1, 'reviewed': True}, 'audio': 'data:audio/wav;base64,'+base64.b64encode(audio.getvalue()).decode()}
    p['sha256'] = sha(js_json(p).encode())
    labels = {'schema': 'fretwork-listening-labels-v1', 'packet_id': p['id'], 'packet_sha256': p['sha256'], 'reviewer': 'reviewer-a', 'independent_ground_truth': False, 'seen_app_predictions': 'no', 'reviewed_whole_take': True, 'labels': [{'start': i+1, 'end': i+1.2, 'kind': k, 'comment': 'synthetic unit fixture, not human evidence'} for i,k in enumerate(('pitch','timing','missing','extra','sustain'))] + [{'start': 10, 'end': 32, 'kind': 'correct', 'comment': 'synthetic fixture'}]}
    approval = {'schema': 'practice-feedback-audit-v1', 'auditor': 'auditor-b', 'packet_sha256': p['sha256'], 'source_sha256': sha(audio.getvalue()), 'rights_confirmed': True, 'real_physical_guitar': True, 'reference_verified': True, 'annotations_verified': True, 'not_used_for_project_tuning': True, 'reviewer_unexposed': True, 'source_identity_verified': True, 'capture_condition_verified': True}
    return p, labels, approval, audio.getvalue()


def manifest(tmp_path, count=6):
    entries = []
    for i in range(count):
        p, labels, approval, audio = bundle(i)
        raw = json.dumps(labels).encode(); approval['labels_sha256'] = sha(raw)
        (tmp_path/f'{i}.packet.json').write_text(json.dumps(p)); (tmp_path/f'{i}.labels.json').write_bytes(raw); (tmp_path/f'{i}.audit.json').write_text(json.dumps(approval)); (tmp_path/f'{i}.wav').write_bytes(audio)
        entries.append({'source_id': f'synthetic-unit-source-{i}', 'source_sha256': sha(audio), 'performer_id': f'synthetic-player-{i%3}', 'condition': ('dry_di','microphone','real_effects')[i%3], 'part': ('rhythm','lead')[i%2], 'packet': f'{i}.packet.json', 'labels': f'{i}.labels.json', 'review_audit': f'{i}.audit.json', 'source_audio': f'{i}.wav'})
    path = tmp_path/'intake.json'; path.write_text(json.dumps({'schema':'practice-feedback-intake-v1','records':entries})); return path


def test_empty_intake_never_calls_inference(tmp_path):
    path = manifest(tmp_path, 0)
    script = "import sys; from benchmarks.practice_feedback.__main__ import main; code=main(sys.argv[1:]); assert 'server.models' not in sys.modules; raise SystemExit(code)"
    result = subprocess.run([os.sys.executable, '-c', script, 'evaluate', '--manifest', str(path), '--out', str(tmp_path/'result.json')], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 3
    report = json.loads((tmp_path/'result.json').read_text()); assert report['inference_run'] is False and report['quality_approved'] is False


def test_declaration_gate_is_not_automatic_quality_approval(tmp_path):
    report, records = audit(manifest(tmp_path)); assert report['status'] == 'eligible_for_evaluation'; assert len(records) == 6
    assert report['quality_approved'] is False and report['inference_run'] is False
    assert 'not authenticated' in report['independence']


@pytest.mark.parametrize('mutation', ['exposed','auditor','checksum','development','duplicate','escape','source','overlap','predictions'])
def test_invalid_independence_and_bindings_block(tmp_path, mutation):
    path = manifest(tmp_path); d = json.loads(path.read_text())
    if mutation == 'development': d['records'][0]['performer_id'] = 'guitarset-player-05'
    elif mutation == 'duplicate': d['records'][1] = deepcopy(d['records'][0])
    elif mutation == 'escape': d['records'][0]['packet'] = '../escape.json'
    elif mutation == 'source': (tmp_path/'0.wav').write_bytes(b'wrong original')
    elif mutation in ('exposed','overlap'):
        f = tmp_path/'0.labels.json'; labels = json.loads(f.read_text())
        if mutation == 'exposed': labels['seen_app_predictions'] = 'yes'
        else: labels['labels'].append({'start': 1, 'end': 2, 'kind': 'correct', 'comment': ''})
        f.write_text(json.dumps(labels))
    elif mutation == 'predictions':
        f = tmp_path/'0.packet.json'; p = json.loads(f.read_text()); p['predictions'] = []; f.write_text(json.dumps(p))
    else:
        f = tmp_path/'0.audit.json'; a = json.loads(f.read_text()); a['auditor' if mutation=='auditor' else 'labels_sha256'] = 'REVIEWER-A' if mutation=='auditor' else '0'*64; f.write_text(json.dumps(a))
    path.write_text(json.dumps(d)); report, _ = audit(path)
    assert report['status'] == 'blocked_missing_coverage' and report['inference_run'] is False


def test_packet_modification_and_audio_window_mismatch_fail():
    p, _, _, _ = bundle(); p['reference']['tuning'] = 'changed'
    with pytest.raises(ValueError, match='checksum'): packet(json.dumps(p))
    p, _, _, _ = bundle(); p['window']['end'] = 30
    with pytest.raises(ValueError, match='duration'): packet(json.dumps(p))


def test_events_are_one_to_one_clustered_and_kind_sensitive():
    findings = [{'kind':'wrong_pitch','take_time':1.05}, {'kind':'wrong_pitch','take_time':1.08}, {'kind':'late','take_time':2}, {'kind':'extra','take_time':4}]
    labels = [{'kind':'pitch','start':1,'end':1.1}, {'kind':'missing','start':2,'end':2.1}, {'kind':'correct','start':3,'end':5}]
    m = event_metrics(findings, labels)
    assert m['by_kind']['pitch']['tp'] == 1
    assert m['by_kind']['missing']['fn'] == 1 and m['by_kind']['timing']['fp'] == 1
    assert m['false_warnings_on_correct'] == 1 and m['false_warnings_per_correct_minute'] == 30


def test_unreviewed_uncertain_regions_and_unsupported_findings_not_hidden():
    m = event_metrics([{'kind':'wrong_pitch','take_time':1},{'kind':'extra','take_time':4},{'kind':'uncertain','target_time':2}], [{'kind':'uncertain','start':.5,'end':1.5}])
    assert m['uncertain_region_prediction_events'] == 1
    assert m['unreviewed_prediction_events'] == 1
    assert m['unsupported_or_uncertain_note_findings'] == 1
    assert m['by_kind']['pitch']['precision'] is None


def test_missing_note_position_uses_recording_clock_and_unknown_alignment_abstains():
    findings = [{'kind':'correct','target_time':0,'take_time':1}, {'kind':'correct','target_time':2,'take_time':5}, {'kind':'missing','target_time':1,'take_time':None}]
    events, _ = cluster_findings(findings); assert events[0]['time'] == 3
    events, abstained = cluster_findings([findings[-1]]); assert events == [] and abstained == 1


def test_boundary_tolerance_does_not_count_a_matched_fault_as_false_correct_warning():
    m = event_metrics([{'kind':'wrong_pitch','take_time':.95}], [{'kind':'correct','start':0,'end':.99},{'kind':'pitch','start':1,'end':1.1}])
    assert m['by_kind']['pitch']['tp'] == 1 and m['false_warnings_on_correct'] == 0


def test_javascript_checksum_number_and_unicode_compatibility():
    if not shutil.which('node'): pytest.skip('Node required only for cross-language serialization check')
    values = {'text':'guitare ♯ café', 'numbers':[0,1.0,1e-7,1e-6,.010000000000000002,59.99999999999999]}
    actual = subprocess.check_output(['node','-e','process.stdout.write(JSON.stringify(JSON.parse(process.argv[1])))',json.dumps(values)], text=True)
    assert js_json(values) == actual


def test_preparation_never_approves_and_never_overwrites_a_review(tmp_path):
    from benchmarks.practice_feedback.prepare import prepare
    p, labels, _, _ = bundle()
    a=tmp_path/'packet.json'; b=tmp_path/'labels.json'; a.write_text(json.dumps(p)); b.write_text(json.dumps(labels))
    out=tmp_path/'private'
    result=prepare(a,b,out,'declared-source','declared-player','dry_di','lead')
    assert result['status']=='pending_external_audit' and result['quality_approved'] is False
    report,_=audit(out/'intake.json'); assert report['status']=='blocked_missing_coverage'
    with pytest.raises(ValueError,match='Duplicate'): prepare(a,b,out,'declared-source','declared-player','dry_di','lead')


@contextmanager
def keep_shared_runtime():
    """A TestClient lifespan deletes the process-wide temp root and shuts down the audio executor.

    Later tests in the same process still need both. This puts the destructive shutdown aside
    for the duration of one client and leaves the shared objects in place afterwards.
    """
    from server import app as app_module
    from server import runtime
    root = runtime.ROOT
    executor = runtime.EXECUTOR
    real_rmtree = app_module.shutil.rmtree
    real_shutdown = executor.shutdown

    def rmtree(path, *args, **kwargs):
        if Path(path) == Path(root):
            return None
        return real_rmtree(path, *args, **kwargs)

    def shutdown(*args, **kwargs):
        return None

    app_module.shutil.rmtree = rmtree
    executor.shutdown = shutdown
    try:
        yield
    finally:
        app_module.shutil.rmtree = real_rmtree
        executor.shutdown = real_shutdown
        root.mkdir(parents=True, exist_ok=True)


def test_api_lifespan_leaves_the_shared_runtime_usable():
    from fastapi.testclient import TestClient
    from server.app import app
    from server import runtime
    root = runtime.ROOT
    with keep_shared_runtime():
        with TestClient(app) as client:
            client.get('/api/not-a-route')
    assert root.is_dir()
    assert runtime.EXECUTOR.submit(lambda: 'still-running').result(timeout=5) == 'still-running'


@pytest.mark.skipif(os.getenv('FRETWORK_RUN_REAL_PRACTICE') != '1', reason='Opt-in actual Basic Pitch inference on real GuitarSet, not a mock')
def test_real_audio_api_against_dataset_annotations():
    from fastapi.testclient import TestClient
    from server.app import app
    from benchmarks.regression.metrics import score_notes
    root = ROOT/'benchmarks/regression/data/guitarset'
    baseline = json.loads((ROOT/'benchmarks/practice_feedback/regression-baseline.json').read_text())
    with keep_shared_runtime(), TestClient(app) as client:
        for stem in ('05_Funk1-114-Ab_solo','05_Jazz2-110-Bb_comp','05_Rock1-90-C#_solo'):
            truth = json.loads((root/f'{stem}.notes.json').read_text())
            assert sha((root/truth['file']).read_bytes()) == baseline['clips'][truth['file']]['audio_sha256']
            assert sha((root/f'{stem}.notes.json').read_bytes()) == baseline['clips'][truth['file']]['annotation_sha256']
            response = client.post('/api/compare', headers={'X-Fretwork-Client':'studio'}, data={'transcriber':'basic_pitch','targets':json.dumps([{'source':'file','notes':truth['notes'],'bpm':truth['tempo']}])}, files={'take':(truth['file'],(root/truth['file']).read_bytes(),'audio/wav')})
            assert response.status_code == 200, response.text
            result = response.json(); assert 'Basic Pitch' in result['transcription']
            metrics = score_notes(result['take_notes'], truth['notes'])
            # Frozen development baseline, not an independently justified accuracy target.
            assert metrics['note_f1'] >= baseline['clips'][truth['file']]['note_f1'] - baseline['allowed_absolute_f1_regression']
            evidence = os.getenv('FRETWORK_REAL_PRACTICE_EVIDENCE')
            if evidence:
                out = Path(evidence); out.mkdir(parents=True, exist_ok=True)
                (out/f'{stem}.json').write_text(json.dumps({'actual_api_and_model':True,'mocked':False,'independent_holdout':False,'audio_sha256':sha((root/truth['file']).read_bytes()),'note_metrics':metrics,'comparison_counts':result['reports'][0]['summary']['counts']},indent=2))
