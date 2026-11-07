# SPDX-License-Identifier: GPL-3.0-or-later
"""Runs YourMT3+ (YPTF.MoE+Multi, noPS) on audio files and writes notes as JSON.

This file is GPL-3.0 because it imports YourMT3's GPL-3.0 code. It is not imported
by Guitar Lab: the engine starts it as a separate program (``python run_yourmt3.py
in.wav out.json ...``) only when ``FRETWORK_TRANSCRIBER=yourmt3`` is chosen.
YourMT3 itself is not copied into this repository; see README.md here."""
import sys, os, json, time
ROOT = os.environ['FRETWORK_YOURMT3_ROOT']
sys.path.insert(0, os.path.join(ROOT, 'amt/src'))
os.chdir(ROOT)
import torch, torchaudio
from collections import Counter
_helper = open(os.path.join(ROOT, 'model_helper.py')).read()
exec(compile(_helper[:_helper.index('def transcribe(model, audio_info):')], 'model_helper.py', 'exec'))  # load_model_checkpoint
from utils.audio import slice_padded_array
from utils.note2event import mix_notes
from utils.event2note import merge_zipped_note_events_and_ties_to_notes
torch.set_num_threads(os.cpu_count())
args = ["mc13_256_g4_all_v7_mt3f_sqr_rms_moe_wf4_n8k2_silu_rope_rp_b36_nops@last.ckpt", '-p', '2024', '-tk', 'mc13_full_plus_256',
        '-dec', 'multi-t5', '-nl', '26', '-enc', 'perceiver-tf', '-sqr', '1', '-ff', 'moe', '-wf', '4', '-nmoe', '8', '-kmoe', '2',
        '-act', 'silu', '-epe', 'rope', '-rp', '1', '-ac', 'spec', '-hop', '300', '-atc', '1', '-pr', '32']
_stdout, sys.stdout = sys.stdout, sys.stderr  # its config dump goes to the log
t0 = time.time(); model = load_model_checkpoint(args=args, device='cpu')
sys.stdout = _stdout; print('loaded in %.1fs' % (time.time()-t0), file=sys.stderr)
for src, dst in zip(sys.argv[1::2], sys.argv[2::2]):
    t0 = time.time()
    import soundfile as sf
    x, sr = sf.read(src, dtype='float32', always_2d=True)
    audio = torch.from_numpy(x.T.copy())
    seconds = audio.shape[1] / sr
    audio = torchaudio.functional.resample(audio.mean(0, keepdim=True), sr, model.audio_cfg['sample_rate'])
    seg = slice_padded_array(audio.numpy(), model.audio_cfg['input_frames'], model.audio_cfg['input_frames'])
    seg = torch.from_numpy(seg.astype('float32')).unsqueeze(1)
    with torch.no_grad():
        pred, _ = model.inference_file(bsz=8, audio_segments=seg)
    starts = [model.audio_cfg['input_frames'] * i / model.audio_cfg['sample_rate'] for i in range(seg.shape[0])]
    per_ch = []
    for ch in range(model.task_manager.num_decoding_channels):
        z, _, _ = model.task_manager.detokenize_list_batches([a[:, ch, :] for a in pred], starts, return_events=True)
        notes, _ = merge_zipped_note_events_and_ties_to_notes(z)
        per_ch.append(notes)
    notes = mix_notes(per_ch)
    out = [{'time': float(n.onset), 'duration': float(max(n.offset - n.onset, 0.01)), 'midi': int(n.pitch), 'program': int(n.program),
            'drum': bool(n.is_drum), 'amplitude': float(n.velocity) / 127 if n.velocity > 1 else 0.7} for n in notes]
    json.dump({'seconds': seconds, 'elapsed': time.time() - t0, 'notes': out}, open(dst, 'w'))
    print(f'{os.path.basename(src)}: {len(out)} notes, {time.time()-t0:.1f}s for {seconds:.1f}s audio', file=sys.stderr)
