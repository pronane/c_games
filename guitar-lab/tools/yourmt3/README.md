# YourMT3+ (optional, for benchmarking)

[YourMT3+](https://github.com/mimbres/YourMT3) (Chang et al., 2024) is a multi-instrument
transcriber. Guitar Lab can call it as an opt-in backend for comparisons. It is not part of the
app and is never on by default.

**Licences.** YourMT3's inference code is GPL-3.0, and its checkpoints on Hugging Face are Apache-2.0.
None of YourMT3 is copied into this repository. `run_yourmt3.py` here imports that code, so it is
GPL-3.0 itself. The engine only ever starts it as a separate program and never imports it.

## Set up

```sh
tools/yourmt3/setup.sh ~/yourmt3            # about 3 GB: code, CPU PyTorch, one 560 MB checkpoint
export FRETWORK_YOURMT3_ROOT=~/yourmt3/code
export FRETWORK_YOURMT3_PYTHON=~/yourmt3/venv/bin/python
python -m benchmarks.regression --tier full --backend basic_pitch --backend yourmt3
```

The checkpoint is YPTF.MoE+Multi (noPS), the model the paper reports at 91.65% note-onset F1 on
GuitarSet. It runs at fp32 on CPU, at roughly real time (about a minute per minute of audio).

`FRETWORK_YOURMT3_PROGRAMS=guitar` keeps only the notes it labels as a General MIDI guitar.
The default keeps every pitched note and drops drums.
