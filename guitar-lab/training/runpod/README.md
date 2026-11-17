# Running the band-mix training on a rented machine

What was actually run on RunPod for `training/FULL_BAND_PLAN.md`.

- `full_run.sh`: download, data build, training, threshold sweep. One command, restartable.
- `fetch_slakh.py`: the dataset over 16 connections (about five times faster than one).
- `sweep.py`, `pick.py`: fair scoring of a retrained model (its own onset threshold, chosen on
  half the validation songs and reported on the other half).

On the machine (any PyTorch + CUDA image, 24 GB card, 250 GB disk):

```bash
git clone https://github.com/pronane/c_games && cd c_games/guitar-lab
pip install -r server/requirements.txt -r server/requirements-models.txt -r server/requirements-transcription.txt \
    -r server/requirements-transcription-extras.txt pretty_midi pyyaml
python -m server.model_store
nohup bash training/runpod/full_run.sh /root/work > /root/full_run.log 2>&1 &
tail /root/work/status
```

The pilot (17 Nov 2026) was run with earlier, hand-written versions of these steps on the
machine itself; those copies were deleted with the machine. Its numbers are in
`benchmarks/regression/RESULTS.md`.
