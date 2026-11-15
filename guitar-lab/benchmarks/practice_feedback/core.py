"""Standard-library intake and localized audible-issue metrics. No model imports here."""
from collections import Counter, defaultdict, deque
from decimal import Decimal
from bisect import bisect_left
import base64
import hashlib
import io
import json
import math
from pathlib import Path
import re
import wave

ROOT = Path(__file__).resolve().parent
PROTOCOL = json.loads((ROOT / 'protocol.json').read_text())
KINDS = ('pitch', 'timing', 'missing', 'extra', 'sustain')
MAP = {'wrong_pitch': 'pitch', 'early': 'timing', 'late': 'timing', 'missing': 'missing', 'extra': 'extra', 'wrong_duration': 'sustain'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def local(root, name):
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError('Expected a local relative file path')
    path = (root / name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError('Missing file or path escapes intake')
    if path.stat().st_size > 50 * 1024 * 1024:
        raise ValueError('Intake file exceeds 50 MB')
    return path


def js_json(value):
    """JSON.stringify-compatible encoding for this bounded packet's scalar schema."""
    if value is None: return 'null'
    if value is True: return 'true'
    if value is False: return 'false'
    if isinstance(value, str): return json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    if isinstance(value, (int, float)):
        if not math.isfinite(value): raise ValueError('Nonfinite JSON number')
        if value == 0: return '0'
        if 1e-6 <= abs(value) < 1e21:
            return format(Decimal(str(value)), 'f').rstrip('0').rstrip('.') if '.' in format(Decimal(str(value)), 'f') else str(int(value))
        mantissa, exponent = format(float(value), '.15g').split('e') if 'e' in format(float(value), '.15g') else (str(value), '0')
        # repr preserves the shortest round-trip value, unlike a fixed precision format.
        if 'e' in repr(float(value)): mantissa, exponent = repr(float(value)).split('e')
        power = int(exponent)
        return mantissa.removesuffix('.0') + 'e' + ('+' if power >= 0 else '-') + str(abs(power))
    if isinstance(value, list): return '[' + ','.join(js_json(x) for x in value) + ']'
    if isinstance(value, dict): return '{' + ','.join(js_json(k) + ':' + js_json(v) for k, v in value.items()) + '}'
    raise ValueError('Unsupported JSON value')


def number(v, low, high):
    return not isinstance(v, bool) and isinstance(v, (int, float)) and math.isfinite(v) and low <= v <= high


def exact(obj, keys):
    if not isinstance(obj, dict) or set(obj) != set(keys): raise ValueError('Unexpected/missing packet fields')


def packet(raw):
    p = json.loads(raw)
    exact(p, ('schema', 'id', 'window', 'reference', 'audio', 'sha256'))
    if p['schema'] != 'fretwork-listening-packet-v1' or not isinstance(p['id'], str) or not 0 < len(p['id']) <= 100: raise ValueError('Invalid packet schema/id')
    w, r = p['window'], p['reference']
    exact(w, ('start', 'end', 'speed')); exact(r, ('notes', 'bpm', 'tuning', 'part', 'revision', 'reviewed'))
    if not number(w['start'], 0, 600) or not number(w['end'], w['start'] + .1, 600) or not number(w['speed'], .5, 1): raise ValueError('Invalid packet window')
    duration = (w['end'] - w['start']) / w['speed']
    if duration > 120.01 or not number(r['bpm'], 10, 400) or type(r['reviewed']) is not bool or not r['reviewed']: raise ValueError('Reference must have been reviewed; invalid duration/tempo')
    if type(r['revision']) is not int or not 1 <= r['revision'] <= 100000: raise ValueError('Invalid reference revision')
    if any(not isinstance(r[k], str) or len(r[k]) > 500 for k in ('part', 'tuning')): raise ValueError('Invalid reference metadata')
    if not isinstance(r['notes'], list) or not 1 <= len(r['notes']) <= 5000: raise ValueError('Need 1–5000 reference notes')
    notes = []
    for n in r['notes']:
        exact(n, ('time', 'duration', 'midi'))
        if not number(n['time'], 0, duration) or not number(n['duration'], 1e-9, duration + .01) or n['time'] + n['duration'] > duration + .01 or type(n['midi']) is not int or not 0 <= n['midi'] <= 127: raise ValueError('Invalid reference note')
        notes.append({k: n[k] for k in ('time', 'duration', 'midi')})
    if not isinstance(p['audio'], str) or not p['audio'].startswith('data:audio/wav;base64,'): raise ValueError('Expected WAV audio')
    audio = base64.b64decode(p['audio'].split(',', 1)[1], validate=True)
    if len(audio) > 30 * 1024 * 1024: raise ValueError('Audio exceeds 30 MB')
    with wave.open(io.BytesIO(audio), 'rb') as f:
        actual = f.getnframes() / f.getframerate()
        if f.getnchannels() not in (1, 2) or abs(actual - duration) > .06: raise ValueError('Audio duration/channel mismatch')
    canonical = {'schema': p['schema'], 'id': p['id'], 'window': {k: w[k] for k in ('start', 'end', 'speed')}, 'reference': {'notes': notes, **{k: r[k] for k in ('bpm', 'tuning', 'part', 'revision', 'reviewed')}}, 'audio': p['audio']}
    if sha(js_json(canonical).encode()) != p['sha256']: raise ValueError('Packet checksum mismatch')
    return p, audio, duration


def union(intervals):
    out = []
    for a, b in sorted(intervals):
        if out and a <= out[-1][1]: out[-1][1] = max(b, out[-1][1])
        else: out.append([a, b])
    return out


def intersects(a, b): return max(a[0], b[0]) < min(a[1], b[1])


def validate_labels(labels, p, duration):
    if labels.get('schema') != 'fretwork-listening-labels-v1' or labels.get('packet_id') != p['id'] or labels.get('packet_sha256') != p['sha256']: raise ValueError('Label/packet binding mismatch')
    if labels.get('independent_ground_truth') is not False: raise ValueError('App review labels must not self-certify ground truth')
    if labels.get('seen_app_predictions') != 'no' or labels.get('reviewed_whole_take') is not True or not isinstance(labels.get('reviewer'), str) or not labels['reviewer'].strip(): raise ValueError('Need a full listening pass by an unexposed reviewer')
    rows = labels.get('labels')
    if not isinstance(rows, list) or not rows or len(rows) > 1000: raise ValueError('Explicit correct/fault coverage required')
    for l in rows:
        if not isinstance(l, dict) or l.get('kind') not in (*KINDS, 'correct', 'uncertain', 'noise') or not number(l.get('start'), 0, duration) or not number(l.get('end'), l['start'], duration) or not isinstance(l.get('comment'), str) or len(l['comment']) > 1000: raise ValueError('Invalid listening annotation')
        if l['kind'] in KINDS and l['end'] - l['start'] > 2: raise ValueError('Fault labels must localize an event within two seconds')
        if l['kind'] == 'correct' and l['end'] <= l['start']: raise ValueError('Correct regions must have positive duration')
    correct = [(l['start'], l['end']) for l in rows if l['kind'] == 'correct']
    faults = [(l['start'], max(l['end'], l['start'] + 1e-9)) for l in rows if l['kind'] != 'correct']
    if any(intersects(c, f) for c in correct for f in faults): raise ValueError('Correct regions overlap fault/uncertain regions')
    uncertain = [(l['start'], l['end']) for l in rows if l['kind'] in ('uncertain', 'noise')]
    if any(intersects((l['start'], max(l['end'], l['start'] + 1e-9)), u) for l in rows if l['kind'] in KINDS for u in uncertain): raise ValueError('Fault overlaps unscored/uncertain region')
    return rows


def audit(manifest):
    manifest = Path(manifest); root = manifest.parent
    if manifest.stat().st_size > 5*1024*1024: raise ValueError('Manifest exceeds 5 MB')
    d = json.loads(manifest.read_text()); reasons = []; records = []
    if d.get('schema') != 'practice-feedback-intake-v1' or not isinstance(d.get('records'), list) or len(d['records']) > 500: raise ValueError('Invalid intake manifest')
    sources, hashes, audio_hashes, ids, performers = set(), set(), set(), set(), set()
    counts = Counter(); kind_sources = defaultdict(set); conditions = set(); parts = set(); correct_seconds = 0
    from benchmarks.holdout.core import PROTOCOL as old_protocol, CATALOG
    excluded_hashes = {sha(x.read_bytes()) for x in CATALOG.glob('*.wav')}
    for entry in d['records']:
        try:
            if not isinstance(entry, dict): raise ValueError('Invalid intake record')
            for k in ('source_id', 'performer_id', 'condition', 'part', 'source_sha256'):
                if not isinstance(entry.get(k), str) or not entry[k].strip(): raise ValueError('Missing source identity/condition/part')
            source, parent = entry['source_id'], entry['source_sha256']
            if source in sources or parent in hashes: raise ValueError('Only one packet per independent physical performance; variants/crops do not count twice')
            if source in old_protocol['excluded_source_ids'] or entry['performer_id'] in old_protocol['excluded_performer_ids'] or parent in excluded_hashes: raise ValueError('Known development material cannot be independent evidence')
            if not re.fullmatch('[0-9a-f]{64}', parent): raise ValueError('Invalid physical-source checksum')
            if entry['condition'] not in PROTOCOL['conditions'] or entry['part'] not in PROTOCOL['parts']: raise ValueError('Unsupported condition/part')
            packet_path = local(root, entry.get('packet')); label_path = local(root, entry.get('labels')); audit_path = local(root, entry.get('review_audit'))
            p, audio, duration = packet(packet_path.read_text())
            original = local(root, entry.get('source_audio'))
            audio_hash = sha(audio)
            if sha(original.read_bytes()) != parent or parent != audio_hash: raise ValueError('Initial feedback intake requires the unmodified standalone physical take; source/audio checksums differ')
            if p['id'] in ids or audio_hash in audio_hashes or audio_hash in excluded_hashes: raise ValueError('Repeated packet/audio or known development waveform')
            raw_labels = label_path.read_bytes(); labels = json.loads(raw_labels)
            rows = validate_labels(labels, p, duration)
            approval = json.loads(audit_path.read_text())
            if approval.get('schema') != 'practice-feedback-audit-v1' or approval.get('packet_sha256') != p['sha256'] or approval.get('labels_sha256') != sha(raw_labels) or approval.get('source_sha256') != parent: raise ValueError('External audit is not bound to packet/labels/source')
            auditor = approval.get('auditor')
            if not isinstance(auditor, str) or not auditor.strip() or auditor.strip().casefold() == labels['reviewer'].strip().casefold(): raise ValueError('A separate auditor is required')
            required = ('rights_confirmed', 'real_physical_guitar', 'reference_verified', 'annotations_verified', 'not_used_for_project_tuning', 'reviewer_unexposed', 'source_identity_verified', 'capture_condition_verified')
            if any(approval.get(k) is not True for k in required): raise ValueError('Independent-review declarations are incomplete')
            # Count overlapping annotations of the same kind only once.
            for kind in KINDS:
                events = union([(l['start'], max(l['end'], l['start'] + 1e-9)) for l in rows if l['kind'] == kind])
                counts[kind] += len(events)
                if events: kind_sources[kind].add(source)
            correct_seconds += sum(b-a for a,b in union([(l['start'], l['end']) for l in rows if l['kind'] == 'correct']))
            sources.add(source); hashes.add(parent); audio_hashes.add(audio_hash); ids.add(p['id']); performers.add(entry['performer_id']); conditions.add(entry['condition']); parts.add(entry['part'])
            records.append({'id': p['id'], 'source_id': source, 'performer_id': entry['performer_id'], 'condition': entry['condition'], 'part': entry['part'], 'packet_sha256': p['sha256'], 'audio_sha256': audio_hash, 'labels_sha256': sha(raw_labels), 'audit_sha256': sha(audit_path.read_bytes()), 'notes': p['reference']['notes'], 'bpm': p['reference']['bpm'], 'audio': audio, 'labels': rows, 'duration': duration})
        except (ValueError, KeyError, TypeError, wave.Error, OSError) as exc:
            reasons.append(str(exc))
    if len(sources) < PROTOCOL['minimum_sources']: reasons.append('Need six independent performances')
    if len(performers) < PROTOCOL['minimum_performers']: reasons.append('Need three independent performers')
    if set(PROTOCOL['conditions']) - conditions: reasons.append('Missing real DI, microphone or real-effects coverage')
    for condition in PROTOCOL['conditions']:
        if sum(r['condition']==condition for r in records) < PROTOCOL['minimum_sources_per_condition']: reasons.append('Need two independent sources for condition: '+condition)
    if set(PROTOCOL['parts']) - parts: reasons.append('Need both rhythm and lead')
    if correct_seconds < PROTOCOL['minimum_correct_seconds']: reasons.append('Need at least 120 explicitly reviewed correct seconds')
    for kind in KINDS:
        if counts[kind] < PROTOCOL['minimum_events_per_kind'] or len(kind_sources[kind]) < 2: reasons.append('Insufficient independent fault coverage: ' + kind)
    return {'schema': 'practice-feedback-audit-result-v1', 'status': 'blocked_missing_coverage' if reasons else 'eligible_for_evaluation', 'reasons': reasons, 'independent_sources': len(sources), 'performers': len(performers), 'audited_records': len(records), 'fault_counts': dict(counts), 'correct_seconds': correct_seconds, 'protocol_sha256': sha((ROOT/'protocol.json').read_bytes()), 'inference_run': False, 'quality_approved': False, 'independence': 'Externally declared, checksum-bound, not authenticated; model-training overlap is unknown.'}, records


def cluster_findings(findings, tolerance=.15):
    supported, abstained = [], 0
    paired = defaultdict(list)
    for n in findings:
        if number(n.get('target_time'), 0, 1200) and number(n.get('take_time'), 0, 1200): paired[n['target_time']].append(n['take_time'])
    anchors = sorted((target, sum(values)/len(values)) for target, values in paired.items())
    def on_take_clock(target):
        i = bisect_left([x[0] for x in anchors], target)
        if i == 0: return target + anchors[0][1] - anchors[0][0]
        if i == len(anchors): return target + anchors[-1][1] - anchors[-1][0]
        a, b = anchors[i-1], anchors[i]
        return a[1] + (target-a[0])*(b[1]-a[1])/(b[0]-a[0])

    for n in findings:
        if n.get('kind') == 'correct': continue
        if n.get('kind') not in MAP: abstained += 1; continue
        t = n.get('take_time')
        if t is None and anchors and number(n.get('target_time'), 0, 1200): t = on_take_clock(n['target_time'])
        if not number(t, 0, 1200): abstained += 1; continue
        supported.append({'kind': MAP[n['kind']], 'time': t})
    clusters = []
    for n in sorted(supported, key=lambda x: (x['kind'], x['time'])):
        if clusters and clusters[-1]['kind'] == n['kind'] and n['time'] - clusters[-1]['time'] <= tolerance: clusters[-1]['note_findings'] += 1
        else: clusters.append({**n, 'note_findings': 1})
    return clusters, abstained


def event_metrics(findings, labels, tolerance=.15):
    predictions, abstained = cluster_findings(findings, tolerance)
    correct = union([(l['start'], l['end']) for l in labels if l['kind'] == 'correct'])
    excluded = [(l['start'], l['end']) for l in labels if l['kind'] in ('uncertain', 'noise')]
    truth = [{'kind': k, 'start': a, 'end': b} for k in KINDS for a,b in union([(l['start'], max(l['end'], l['start'] + 1e-9)) for l in labels if l['kind'] == k])]
    before_mask = len(predictions)
    predictions = [p for p in predictions if not any(a <= p['time'] <= b for a,b in excluded)]
    # Only explicit reviewed coverage is eligible for precision. Near a labelled fault is covered.
    covered = lambda t: any(a <= t <= b for a,b in correct) or any(x['start']-tolerance <= t <= x['end']+tolerance for x in truth)
    evaluated = [p for p in predictions if covered(p['time'])]
    edges = [[j for j,p in enumerate(evaluated) if p['kind'] == t['kind'] and t['start']-tolerance <= p['time'] <= t['end']+tolerance] for t in truth]
    assigned, by_truth = {}, {}
    for i in range(len(truth)):
        queue, seen_truth, pred_parent, free = deque([i]), {i}, {}, None
        while queue and free is None:
            t = queue.popleft()
            for j in edges[t]:
                if j in pred_parent: continue
                pred_parent[j] = t
                if j not in assigned: free = j; break
                previous = assigned[j]
                if previous not in seen_truth: seen_truth.add(previous); queue.append(previous)
        while free is not None:
            t = pred_parent[free]; previous = by_truth.get(t)
            assigned[free] = t; by_truth[t] = free; free = previous
    matched = set(assigned.values()); rows = {}
    for kind in KINDS:
        tp = sum(truth[i]['kind'] == kind for i in matched); pred = sum(p['kind'] == kind for p in evaluated); total = sum(t['kind'] == kind for t in truth)
        precision = tp / pred if pred else None; recall = tp / total if total else None
        rows[kind] = {'tp': tp, 'fp': pred-tp, 'fn': total-tp, 'precision': precision, 'recall': recall, 'f1': 2*tp/(pred+total) if pred+total else None}
    false_correct = sum(j not in assigned and any(a <= p['time'] <= b for a,b in correct) for j,p in enumerate(evaluated))
    seconds = sum(b-a for a,b in correct)
    return {'by_kind': rows, 'false_warnings_on_correct': false_correct, 'correct_seconds': seconds, 'false_warnings_per_correct_minute': false_correct * 60 / seconds if seconds else None, 'uncertain_region_prediction_events': before_mask-len(predictions), 'unreviewed_prediction_events': len(predictions)-len(evaluated), 'unsupported_or_uncertain_note_findings': abstained, 'evaluated_prediction_events': len(evaluated), 'truth_events': len(truth), 'event_tolerance_s': tolerance}
