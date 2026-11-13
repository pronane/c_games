"""Synthetic schema fixtures only. These are NOT human-labelled evaluation data."""
import json
from pathlib import Path
import struct
import wave

import pytest

from benchmarks.holdout.core import audit, sha256, PROTOCOL
from benchmarks.holdout.__main__ import main


def fixture(tmp_path, *, source='new-source-1', performer='new-player-1', condition='dry', index=1):
    audio=tmp_path/f'audio-{index}.wav'
    with wave.open(str(audio),'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(8000)
        w.writeframes(struct.pack('<h',index)*16000)
    labels={'source_sha256':sha256(audio),'review_status':'human_verified','reviewer':'unit-test-fixture-not-real-review',
            'notes':[{'id':'n1','time':.2,'duration':.4,'midi':64}],
            'sustain':[{'note_id':'n1','expected_duration':.4,'judgement':'correct','basis':'synthetic unit fixture, not evidence'}]}
    labelpath=tmp_path/f'labels-{index}.json';labelpath.write_text(json.dumps(labels))
    clip={'id':f'clip-{index}','source_id':source,'source_sha256':f'{index:064x}',
          'performer_id':performer,'condition':condition,'capture':'real','split':'evaluation','rights_confirmed':True,
          'audio':audio.name,'sha256':sha256(audio),'labels':labelpath.name,'labels_sha256':sha256(labelpath)}
    return clip,labels,labelpath


def save(tmp_path,clips):
    p=tmp_path/'intake.json';p.write_text(json.dumps({'protocol':PROTOCOL['version'],'clips':clips}));return p


def relabel(clip,labels,path):
    path.write_text(json.dumps(labels));clip['labels_sha256']=sha256(path)


def test_empty_intake_blocks_and_never_runs_inference(tmp_path,monkeypatch):
    p=save(tmp_path,[]);out=tmp_path/'report.json'
    monkeypatch.setattr('benchmarks.holdout.__main__.evaluate',lambda records: pytest.fail('Must not run a model'))
    assert main(['evaluate','--manifest',str(p),'--out',str(out)])==3
    data=json.loads(out.read_text())
    assert data['status']=='blocked_missing_coverage'
    assert data['inference_run'] is False and data['quality_approved'] is False
    assert data['independent_performers']==0


def test_one_valid_clip_is_not_a_complete_holdout(tmp_path):
    clip,_,_=fixture(tmp_path);report,records=audit(save(tmp_path,[clip]))
    assert len(records)==1 and report['missing']
    assert report['independent_performances']==1
    assert report['quality_approved'] is False


@pytest.mark.parametrize('field,value', [('review_status','pending_human_review'),('reviewer',''),('source_sha256','wrong')])
def test_unverified_or_mismatched_labels_fail(tmp_path,field,value):
    clip,labels,path=fixture(tmp_path);labels[field]=value;relabel(clip,labels,path)
    with pytest.raises(ValueError):audit(save(tmp_path,[clip]))


@pytest.mark.parametrize('field,value', [('time',-1),('duration',0),('duration',float('nan')),('midi',64.5),('midi',True),('midi',128),('time',1.9),('id','')])
def test_invalid_note_boundaries_pitches_and_ids_fail(tmp_path,field,value):
    clip,labels,path=fixture(tmp_path);labels['notes'][0][field]=value;relabel(clip,labels,path)
    with pytest.raises(ValueError):audit(save(tmp_path,[clip]))


@pytest.mark.parametrize('field,value',[('note_id','absent'),('expected_duration',0),('judgement','model_says_short'),('basis','')])
def test_sustain_requires_human_reference_and_known_note(tmp_path,field,value):
    clip,labels,path=fixture(tmp_path);labels['sustain'][0][field]=value;relabel(clip,labels,path)
    with pytest.raises(ValueError):audit(save(tmp_path,[clip]))


@pytest.mark.parametrize('field,value',[('performer_id','05'),('source_id','gs_rock_solo'),('split','development'),('rights_confirmed',False),('condition','unknown'),('source_sha256','unknown')])
def test_nonheldout_or_unconsented_sources_fail(tmp_path,field,value):
    clip,_,_=fixture(tmp_path);clip[field]=value
    with pytest.raises(ValueError):audit(save(tmp_path,[clip]))


@pytest.mark.parametrize('name',['../escape.wav','/tmp/escape.wav'])
def test_path_escape_rejected(tmp_path,name):
    clip,_,_=fixture(tmp_path);clip['audio']=name
    with pytest.raises(ValueError):audit(save(tmp_path,[clip]))


def test_symlink_escape_rejected(tmp_path):
    clip,_,_=fixture(tmp_path);outside=tmp_path.parent/'outside-holdout.bin';outside.write_bytes(b'test')
    link=tmp_path/'linked.wav';link.symlink_to(outside);clip['audio']=link.name
    try:
        with pytest.raises(ValueError):audit(save(tmp_path,[clip]))
    finally:outside.unlink()


def test_duplicate_audio_cannot_be_counted_as_two_performances(tmp_path):
    a,_,_=fixture(tmp_path,index=1);b,_,_=fixture(tmp_path,index=2,source='new-source-2')
    b['audio']=a['audio'];b['sha256']=a['sha256']
    with pytest.raises(ValueError,match='Identical audio'):audit(save(tmp_path,[a,b]))


def test_same_parent_cannot_be_given_two_source_ids(tmp_path):
    a,_,_=fixture(tmp_path,index=1);b,_,_=fixture(tmp_path,index=2,source='new-source-2');b['source_sha256']=a['source_sha256']
    with pytest.raises(ValueError,match='Parent recordings'):audit(save(tmp_path,[a,b]))


def test_derived_conditions_count_as_one_source_and_one_sustain_example(tmp_path):
    a,_,_=fixture(tmp_path,index=1);b,_,_=fixture(tmp_path,index=2,condition='quiet_dry');b['source_sha256']=a['source_sha256']
    report,_=audit(save(tmp_path,[a,b]))
    assert report['clips']==2 and report['independent_performances']==1
    assert report['sustain_examples']['correct']==1


def test_synthetic_room_does_not_count_as_real_wet_coverage(tmp_path):
    clip,_,_=fixture(tmp_path,condition='wet');clip['capture']='synthetic'
    report,_=audit(save(tmp_path,[clip]))
    assert report['independent_performances']==0
    assert next(m for m in report['missing'] if m['requirement']=='wet performances')['available']==0


def test_malformed_intake_has_nonzero_exit_and_no_quality_claim(tmp_path):
    path=tmp_path/'bad.json';path.write_text('{}');out=tmp_path/'out.json'
    assert main(['audit','--manifest',str(path),'--out',str(out)])==1
    assert json.loads(out.read_text())['status']=='invalid_intake'


def test_prepare_does_not_overwrite_review_work(tmp_path):
    from benchmarks.holdout.prepare_review import prepare
    out=tmp_path/'existing';out.mkdir();(out/'human.json').write_text('keep')
    with pytest.raises(ValueError,match='never overwritten'):prepare(tmp_path/'absent.wav',out)
    assert (out/'human.json').read_text()=='keep'


def test_complete_paired_coverage_is_not_quality_approval(tmp_path,monkeypatch):
    for key in ('minimum_performers','minimum_independent_performances','minimum_independent_performances_per_condition','minimum_correct_sustain_examples','minimum_sustain_performances'):
        monkeypatch.setitem(PROTOCOL,key,1)
    monkeypatch.setitem(PROTOCOL,'minimum_short_sustain_examples',0)
    monkeypatch.setitem(PROTOCOL,'minimum_long_sustain_examples',0)
    clips=[]
    for i,condition in enumerate(PROTOCOL['required_conditions'],1):
        clip,_,_=fixture(tmp_path,index=i,condition=condition);clip['source_sha256']=f'{1:064x}';clips.append(clip)
    report,_=audit(save(tmp_path,clips))
    assert not report['missing'] and report['status']=='coverage_ready_not_quality_approved'
    assert report['quality_approved'] is False and report['inference_run'] is False


def test_conflicting_labels_across_effect_variants_fail(tmp_path):
    a,_,_=fixture(tmp_path,index=1);b,labels,path=fixture(tmp_path,index=2,condition='wet')
    b['source_sha256']=a['source_sha256'];labels['sustain'][0]['judgement']='too_short';relabel(b,labels,path)
    with pytest.raises(ValueError,match='Conflicting human'):audit(save(tmp_path,[a,b]))


def test_known_development_audio_hash_fails_even_with_new_aliases(tmp_path):
    from benchmarks.holdout.core import CATALOG
    path=next(CATALOG.glob('*.wav'));clip,_,_=fixture(tmp_path)
    # Even a declared new performer/source cannot reuse a known parent recording.
    clip['source_sha256']=sha256(path)
    with pytest.raises(ValueError,match='independent parent'):audit(save(tmp_path,[clip]))


def test_evaluator_keeps_raw_sustain_counts_and_restores_flag(monkeypatch):
    import os
    from server import models
    from benchmarks.holdout.__main__ import evaluate
    calls=[]
    def fake(path,**kwargs):
        calls.append((path,dict(kwargs),os.environ['FRETWORK_RILEY_LEVEL_GUARD']))
        return [{'time':.2,'duration':.4,'midi':64}]
    monkeypatch.setattr(models,'transcribe',fake)
    monkeypatch.setenv('FRETWORK_RILEY_LEVEL_GUARD','previous-value')
    record={'id':'test-clip','source_id':'test-source','performer_id':'test-player','condition':'dry',
            'capture':'real','audio_path':'not-read-by-mock.wav','audio_sha256':'test','labels_sha256':'test',
            'notes':[{'id':'note','time':.2,'duration':.4,'midi':64}],
            'sustain':[{'note_id':'note','expected_duration':.4,'judgement':'correct','basis':'unit fixture'}]}
    result=evaluate([record])
    assert [x[2] for x in calls]==['0','1']
    assert all(x[1]=={'backend':'riley','midi_min':40,'midi_max':88} for x in calls)
    assert os.environ['FRETWORK_RILEY_LEVEL_GUARD']=='previous-value'
    assert result['quality_approved'] is False
    assert result['rows'][0]['raw_sustain_counts']=={'correct_total':1,'correct_matched':1,'correct_not_flagged':1}
    assert result['source_bootstrap_95_percent_interval'] is None


def test_evaluator_restores_flag_after_inference_failure(monkeypatch):
    import os
    from server import models
    from benchmarks.holdout.__main__ import evaluate
    def fail(*args,**kwargs):raise RuntimeError('test failure')
    monkeypatch.setattr(models,'transcribe',fail)
    monkeypatch.delenv('FRETWORK_RILEY_LEVEL_GUARD',raising=False)
    with pytest.raises(RuntimeError):evaluate([{'audio_path':'test','notes':[]}])
    assert 'FRETWORK_RILEY_LEVEL_GUARD' not in os.environ
