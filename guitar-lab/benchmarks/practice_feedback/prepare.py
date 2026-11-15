"""Copy a reviewer packet into PRIVATE intake; create a pending, never-approved audit form."""
import argparse
import json
from pathlib import Path
from .core import packet, sha, validate_labels, PROTOCOL


def prepare(packet_path, labels_path, destination, source, performer, condition, part):
    if not source.strip() or not performer.strip() or condition not in PROTOCOL['conditions'] or part not in PROTOCOL['parts']:
        raise ValueError('Declare physical source/performer aliases, capture condition and part')
    if Path(packet_path).stat().st_size > 45*1024*1024 or Path(labels_path).stat().st_size > 3*1024*1024: raise ValueError('Input exceeds packet/label limits')
    raw_packet = Path(packet_path).read_bytes(); raw_labels = Path(labels_path).read_bytes()
    if len(raw_packet) > 45*1024*1024 or len(raw_labels) > 3*1024*1024: raise ValueError('Input exceeds packet/label limits')
    p, audio, duration = packet(raw_packet); labels = json.loads(raw_labels); validate_labels(labels, p, duration)
    destination = Path(destination); path = destination/'intake.json'
    manifest = json.loads(path.read_text()) if path.exists() else {'schema':'practice-feedback-intake-v1','records':[]}
    if manifest.get('schema') != 'practice-feedback-intake-v1' or not isinstance(manifest.get('records'), list): raise ValueError('Invalid existing intake')
    if any(r['source_id']==source or r['source_sha256']==sha(audio) for r in manifest['records']): raise ValueError('Duplicate physical source/audio; do not count variants twice')
    prefix = sha(p['id'].encode())[:20]
    names = {'packet':prefix+'.packet.json','labels':prefix+'.labels.json','review_audit':prefix+'.audit.pending.json','source_audio':prefix+'.wav'}
    if any((destination/name).exists() for name in names.values()): raise ValueError('Prepared files already exist; never overwrite reviews')
    pending = {'schema':'practice-feedback-audit-v1','auditor':'','packet_sha256':p['sha256'],'labels_sha256':sha(raw_labels),'source_sha256':sha(audio),
               **{k:False for k in ('rights_confirmed','real_physical_guitar','reference_verified','annotations_verified','not_used_for_project_tuning','reviewer_unexposed','source_identity_verified','capture_condition_verified')},
               'instructions':'A separate human auditor must verify these declarations and the original standalone physical take. Do not approve synthetic tests, development clips, crops or transformed variants as independent sources.'}
    destination.mkdir(parents=True, exist_ok=True)
    (destination/names['packet']).write_bytes(raw_packet); (destination/names['labels']).write_bytes(raw_labels); (destination/names['source_audio']).write_bytes(audio)
    (destination/names['review_audit']).write_text(json.dumps(pending,indent=2)+'\n')
    manifest['records'].append({'source_id':source,'source_sha256':sha(audio),'performer_id':performer,'condition':condition,'part':part,**names})
    path.write_text(json.dumps(manifest,indent=2)+'\n')
    return {'manifest':str(path),'status':'pending_external_audit','quality_approved':False,'inference_run':False}


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--packet',required=True,type=Path); p.add_argument('--labels',required=True,type=Path); p.add_argument('--out',required=True,type=Path)
    p.add_argument('--source',required=True); p.add_argument('--performer',required=True); p.add_argument('--condition',required=True,choices=PROTOCOL['conditions']); p.add_argument('--part',required=True,choices=PROTOCOL['parts'])
    a=p.parse_args()
    try: print(json.dumps(prepare(a.packet,a.labels,a.out,a.source,a.performer,a.condition,a.part))); return 0
    except (ValueError,OSError,KeyError,TypeError) as e: print(json.dumps({'status':'error','error':str(e),'inference_run':False})); return 2


if __name__ == '__main__': raise SystemExit(main())
