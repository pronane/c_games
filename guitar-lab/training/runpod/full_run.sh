#!/bin/bash
# The whole of training/FULL_BAND_PLAN.md steps 3 to 5 on a rented machine, start to finish.
# Safe to run again after an interruption: the download, the build and the training each
# continue from where they stopped.
#
#   bash training/runpod/full_run.sh /root/work
#
# Settings (environment): STEPS (20000), EVERY (2500), SHARDS (3 build processes),
# VAL_TRACKS (40 validation songs for the threshold sweep), BUILD_SHIFTS (1; the app uses 2,
# which doubles the separation time. Scoring always uses the app's setting).
# Progress is written to <work>/status; results to <work>/results.json.
set -u
export FRETWORK_DEVICE=cuda
export OMP_NUM_THREADS=3 MKL_NUM_THREADS=3 OPENBLAS_NUM_THREADS=3 NUMBA_NUM_THREADS=3 NUMEXPR_NUM_THREADS=3
W=${1:-/root/work}
RUNS=${RUNS:-$W/runs}   # put this on a network volume so checkpoints outlive the machine
STEPS=${STEPS:-20000}; EVERY=${EVERY:-2500}; SHARDS=${SHARDS:-3}; VAL=${VAL_TRACKS:-40}
mkdir -p "$W"
cd "$(dirname "$0")/../.." || exit 1
S=$W/status
step() { echo "$(date -u +%FT%T) $1" >> "$S"; }
fail() { step "FAILED $1"; exit 1; }
SL=$W/slakh2100_flac_redux

if [ ! -f "$W/download_done" ]; then
  step download
  python training/runpod/fetch_slakh.py 2> "$W/fetch.log" \
    | tar xz --no-same-owner -C "$W" --wildcards '*/train/*' '*/validation/*' > "$W/tar.log" 2>&1
  grep -q FETCH_COMPLETE "$W/fetch.log" || fail download
  touch "$W/download_done"
fi
step "extracted train=$(ls "$SL/train" | wc -l) validation=$(ls "$SL/validation" | wc -l)"

# The released model on the validation songs. Runs beside the build and fills the cache of
# separated validation audio that the later sweeps reuse.
if [ ! -f "$W/sweep_released.done" ]; then
  ( python training/runpod/sweep.py released "$SL/validation" "$W/sweepcache" --tracks "$VAL" > "$W/sweep_released.log" 2>&1 \
      && touch "$W/sweep_released.done" ) &
  RELEASED=$!
fi

if [ ! -f "$W/build_done" ]; then
  step build
  pids=()
  for i in $(seq 0 $((SHARDS - 1))); do
    FRETWORK_DEMUCS_SHIFTS=${BUILD_SHIFTS:-1} python -m training.slakh_data build "$SL/train" "$W/data" \
      --also-mix --also-stem --shard "$i/$SHARDS" >> "$W/build_$i.log" 2>&1 &
    pids+=($!)
  done
  for p in "${pids[@]}"; do wait "$p" || fail build; done
  touch "$W/build_done"
fi
step "build_done segments=$(ls "$W/data" | grep -c '^seg_')"
[ -n "${RELEASED:-}" ] && wait "$RELEASED"
[ -f "$W/sweep_released.done" ] || fail sweep_released

if [ ! -f "$W/train_done" ]; then
  last=$(ls "$RUNS" 2>/dev/null | sed -n 's/^step_\([0-9]*\)\.pth$/\1/p' | sort -n | tail -1)
  resume=()
  [ -n "$last" ] && resume=(--init "$RUNS/step_$last.pth" --start "$last")
  step "train from ${last:-0}"
  OMP_NUM_THREADS=6 python -m training.finetune_riley --data "$W/data" --out "$RUNS" --steps "$STEPS" --every "$EVERY" \
    --batch 16 --workers 6 "${resume[@]}" >> "$W/train.log" 2>&1 || fail train
  touch "$W/train_done"
fi
step train_done

# Sweep the last checkpoint and the one with the lowest validation loss.
best=$(grep -E '^step [0-9]+ validation' "$W/train.log" | sort -k4 -n | head -1 | awk '{print $2}')
logs=("$W/sweep_released.log")
for s in $(printf '%s\n' "$STEPS" "$best" | sort -un); do
  [ -f "$RUNS/step_$s.pth" ] || continue
  step "sweep step $s"
  [ -f "$W/sweep_$s.done" ] || { FRETWORK_RILEY_CHECKPOINT="$RUNS/step_$s.pth" python training/runpod/sweep.py "step$s" "$SL/validation" "$W/sweepcache" \
      --tracks "$VAL" > "$W/sweep_$s.log" 2>&1 && touch "$W/sweep_$s.done"; }
  logs+=("$W/sweep_$s.log")
done
python training/runpod/pick.py "${logs[@]}" > "$W/results.json" 2>> "$W/status" || fail pick
step DONE
