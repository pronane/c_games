"""Fail-closed holdout intake. Standard library only; audit never imports a model."""
from collections import Counter, defaultdict
import hashlib
import json
import math
import re
from pathlib import Path
import wave

ROOT = Path(__file__).resolve().parent
PROTOCOL = json.loads((ROOT/'protocol.json').read_text())
CATALOG = ROOT.parent/'regression'/'data'/'guitarset'


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def local_file(root, name):
    if not isinstance(name,str) or not name or Path(name).is_absolute():
        raise ValueError('File paths must be nonempty relative paths inside the intake directory')
    p = (root/name).resolve()
    if not p.is_relative_to(root.resolve()):
        raise ValueError('File escapes the intake directory')
    if not p.is_file():
        raise ValueError(f'Missing intake file: {name}')
    return p


def number(value, name, minimum=0):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value < minimum:
        raise ValueError(f'{name} must be a finite number >= {minimum}')
    return float(value)


def validate_labels(labels, audio_hash, duration):
    if labels.get('source_sha256') != audio_hash:
        raise ValueError('Human labels do not match the audio checksum')
    if labels.get('review_status') != 'human_verified' or not str(labels.get('reviewer','')).strip():
        raise ValueError('Labels require a named/aliased human reviewer and human_verified status')
    notes = labels.get('notes')
    if not isinstance(notes,list) or not notes:
        raise ValueError('At least one human-reviewed note is required')
    ids = set()
    for n in notes:
        if not isinstance(n.get('id'),str) or not n['id'] or n['id'] in ids:
            raise ValueError('Human note ids must be nonempty and unique')
        ids.add(n['id'])
        start=number(n.get('time'),'note onset'); length=number(n.get('duration'),'note duration',.01)
        midi=n.get('midi')
        if isinstance(midi,bool) or not isinstance(midi,int) or not 0 <= midi <= 127:
            raise ValueError('Note MIDI must be an integer 0..127')
        if start+length > duration+.02:
            raise ValueError('Note extends beyond audio')
    by_id={n['id']:n for n in notes}
    examples=labels.get('sustain',[])
    if not isinstance(examples,list):
        raise ValueError('sustain must be a list')
    seen=set()
    for e in examples:
        key=e.get('note_id')
        if key not in by_id or key in seen:
            raise ValueError('Sustain examples require unique existing note_id values')
        seen.add(key)
        expected=number(e.get('expected_duration'),'expected duration',.01)
        if by_id[key]['time']+expected > duration+.02:
            raise ValueError('Expected sustain extends beyond the review window')
        if e.get('judgement') not in ('correct','too_short','too_long'):
            raise ValueError('Sustain judgement must be human-labelled correct/too_short/too_long')
        if not str(e.get('basis','')).strip():
            raise ValueError('Sustain examples require a human basis (score, reference, or listening rationale)')
    return notes, examples


def audit(manifest_path):
    path=Path(manifest_path);root=path.parent.resolve()
    manifest=json.loads(path.read_text())
    if manifest.get('protocol') != PROTOCOL['version']:
        raise ValueError('Manifest protocol version mismatch')
    clips=manifest.get('clips')
    if not isinstance(clips,list):
        raise ValueError('clips must be a list')
    excluded={sha256(p) for p in CATALOG.glob('*.wav')}
    private_manifest=ROOT.parent/'evidence'/'private_manifest.json'
    if private_manifest.is_file():
        excluded.add(json.loads(private_manifest.read_text())['source_sha256'])
    records=[];ids=set();audio_hashes=set();owners={};sources=defaultdict(set)
    parent_owners={};source_parents={}
    for clip in clips:
        cid=clip.get('id')
        if not isinstance(cid,str) or not cid or cid in ids:
            raise ValueError('Clip ids must be unique and nonempty')
        ids.add(cid)
        source=clip.get('source_id');performer=clip.get('performer_id')
        if not isinstance(source,str) or not source.strip() or not isinstance(performer,str) or not performer.strip():
            raise ValueError('source_id and performer_id are required')
        if source in PROTOCOL['excluded_source_ids'] or performer in PROTOCOL['excluded_performer_ids']:
            raise ValueError('Known development performer/source is not held out')
        parent=clip.get('source_sha256','')
        if not isinstance(parent,str) or not re.fullmatch(r'[0-9a-f]{64}',parent) or parent in excluded:
            raise ValueError('Valid independent parent-recording source_sha256 is required')
        if parent_owners.setdefault(parent,source) != source or source_parents.setdefault(source,parent) != parent:
            raise ValueError('Parent recordings cannot be split into multiple independent source ids')
        if owners.setdefault(source,performer) != performer:
            raise ValueError('One performance cannot have conflicting performer ids')
        if clip.get('split') != 'evaluation' or clip.get('rights_confirmed') is not True:
            raise ValueError('Evaluation split and confirmed recording rights are required')
        condition=clip.get('condition')
        if condition not in PROTOCOL['required_conditions']:
            raise ValueError('Unknown condition')
        audio=local_file(root,clip.get('audio'));ah=sha256(audio)
        if ah != clip.get('sha256') or ah in excluded:
            raise ValueError('Audio checksum mismatch or known development audio')
        if ah in audio_hashes:
            raise ValueError('Identical audio cannot be relabelled as another condition or source')
        audio_hashes.add(ah)
        labels_path=local_file(root,clip.get('labels'))
        if sha256(labels_path) != clip.get('labels_sha256'):
            raise ValueError('Labels checksum mismatch')
        with wave.open(str(audio),'rb') as wav:
            duration=wav.getnframes()/wav.getframerate()
            if not .4 <= duration <= 60 or wav.getnchannels() not in (1,2):
                raise ValueError('Intake requires mono/stereo PCM WAV, .4 to 60 seconds')
        labels=json.loads(labels_path.read_text())
        notes,examples=validate_labels(labels,ah,duration)
        capture=clip.get('capture')
        if capture not in ('real','synthetic'):
            raise ValueError('capture must identify real or synthetic effects')
        sources[condition].add(source) if capture=='real' else None
        records.append({'id':cid,'source_id':source,'performer_id':performer,'condition':condition,
                        'capture':capture,'source_sha256':parent,'audio_path':str(audio),'audio_sha256':ah,
                        'labels_sha256':clip['labels_sha256'],'duration_s':duration,
                        'notes':notes,'sustain':examples})
    real=[r for r in records if r['capture']=='real']
    performers={r['performer_id'] for r in real};performances={r['source_id'] for r in real}
    # Count sustain examples once per source/note id, not again for gain/room variants.
    examples={};sustain_sources=set();condition_note_ids=set()
    for r in real:
        for e in r['sustain']:
            condition_key=(r['source_id'],r['condition'],e['note_id'])
            if condition_key in condition_note_ids:
                raise ValueError('Overlapping sustain examples cannot be counted twice in one condition')
            condition_note_ids.add(condition_key)
            key=(r['source_id'],e['note_id'])
            old=examples.setdefault(key,e['judgement'])
            if old != e['judgement']:
                raise ValueError('Conflicting human sustain judgement across variants of a performance')
            sustain_sources.add(r['source_id'])
    counts=Counter(examples.values());missing=[]
    def require(label,got,minimum):
        if got < minimum:missing.append({'requirement':label,'available':got,'required':minimum})
    require('independent performers',len(performers),PROTOCOL['minimum_performers'])
    require('independent performances',len(performances),PROTOCOL['minimum_independent_performances'])
    paired=set.intersection(*(sources[c] for c in PROTOCOL['required_conditions']))
    require('paired performances across all four conditions',len(paired),PROTOCOL['minimum_independent_performances'])
    for condition in PROTOCOL['required_conditions']:
        require(condition+' performances',len(sources[condition]),PROTOCOL['minimum_independent_performances_per_condition'])
    for judgement,key in [('correct','minimum_correct_sustain_examples'),('too_short','minimum_short_sustain_examples'),('too_long','minimum_long_sustain_examples')]:
        require(judgement+' human sustain examples',counts[judgement],PROTOCOL[key])
    require('sustain-labelled performances',len(sustain_sources),PROTOCOL['minimum_sustain_performances'])
    report={'inference_run':False,'quality_approved':False,'status':'blocked_missing_coverage' if missing else 'coverage_ready_not_quality_approved',
            'protocol':PROTOCOL['version'],'protocol_sha256':sha256(ROOT/'protocol.json'),
            'manifest_sha256':sha256(path),'clips':len(records),'independent_performers':len(performers),
            'independent_performances':len(performances),'sustain_examples':dict(counts),'missing':missing,
            'limits':['Human provenance is declared, not independently authenticated.',
                      'Held out from project tuning, not guaranteed unseen by model training.',
                      'Coverage readiness is not quality approval; no defaults are promoted.']}
    return report,records
