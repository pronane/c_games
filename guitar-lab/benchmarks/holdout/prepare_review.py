"""Prepare unlabelled local review windows. Never infers or certifies any note.

python -m benchmarks.holdout.prepare_review --audio /local/take.aac --out /local/private/review
Requires ffmpeg on PATH, or imageio-ffmpeg. Audio and generated packets must stay out of Git.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import wave
import zipfile

from .core import sha256, ROOT


def prepare(audio, out, starts=(0,145,290), seconds=10):
    audio=Path(audio);out=Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError('Use a new/empty review directory; existing work is never overwritten')
    out.mkdir(parents=True,exist_ok=True)
    ff=shutil.which('ffmpeg')
    if not ff:
        import imageio_ffmpeg
        ff=imageio_ffmpeg.get_ffmpeg_exe()
    parent_hash=sha256(audio);windows=[]
    for start in starts:
        path=out/f'window-{start:04d}.wav'
        subprocess.run([ff,'-v','error','-nostdin','-y','-ss',str(start),'-i',str(audio),'-t',str(seconds),
                        '-ac','1','-ar','22050','-c:a','pcm_s16le',str(path)],check=True)
        with wave.open(str(path),'rb') as w:
            duration=w.getnframes()/w.getframerate()
        if duration<.4:
            path.unlink();continue
        labels={'source_sha256':sha256(path),'review_status':'pending_human_review','reviewer':'',
                'notes':[],'sustain':[]}
        labelpath=out/f'{path.stem}.pending-labels.json';labelpath.write_text(json.dumps(labels,indent=2)+'\n')
        windows.append({'audio':path.name,'start_in_parent_s':start,'duration_s':duration,
                        'sha256':labels['source_sha256'],'pending_labels':labelpath.name})
    metadata={'parent_sha256':parent_hash,'role':'development_review_only_not_independent_holdout',
              'review_status':'pending_human_review','human_review_completed':False,'windows':windows,
              'warning':'No note, pitch, direct-note offset, sustain error or dry/wet condition has been inferred. Do not count this previously used recording as independent holdout data.'}
    (out/'packet.json').write_text(json.dumps(metadata,indent=2)+'\n')
    shutil.copyfile(ROOT/'review.html',out/'review.html')
    (out/'READ_ME.txt').write_text('Open review.html in a modern browser (or serve this folder locally). Select each window WAV.\nListen, enter only verified notes/direct-note ends, and state the basis for sustain judgements.\nExport human-labels.json for each window and keep the filenames distinct. Do not edit pending JSON to claim review without listening.\nThis packet is development review material, not independent held-out evidence. Audio stays in the browser; no external service is called.\nNo accuracy score is available until human labels exist. See packet.json for parent timestamps.\n')
    archive=out.with_suffix('.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.iterdir()):
            if p.is_file():z.write(p,p.name)
    return metadata,archive


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--audio',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();metadata,archive=prepare(a.audio,a.out)
    print(json.dumps({'windows':len(metadata['windows']),'human_review_completed':False,'archive':str(archive)}))


if __name__=='__main__':main()
