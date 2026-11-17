#!/bin/bash
# Riley fine-tuned on real recordings (MoisesDB), start to finish. Restartable.
#
#   bash training/runpod/moises_run.sh <link file> <test songs.json> /root/mw
#
# Checkpoint and onset threshold are chosen on the validation songs (separated with
# BS-RoFormer SW); the test songs are only scored at the end. Status in <work>/status.
set -u
export FRETWORK_DEVICE=cuda OMP_NUM_THREADS=3 MKL_NUM_THREADS=3 NUMBA_NUM_THREADS=3
LINK=$1; TEST=$2; W=$3; STEPS=${STEPS:-6000}; EVERY=${EVERY:-1000}
mkdir -p "$W"; cd "$(dirname "$0")/../.." || exit 1
S=$W/status
step() { echo "$(date -u +%FT%T) $1" >> "$S"; }
fail() { step "FAILED $1"; exit 1; }
[ -f "$W/prepare_done" ] || { step prepare; python -m training.moises_data prepare "$LINK" "$TEST" "$W" >> "$W/prepare.log" 2>&1 || fail prepare; touch "$W/prepare_done"; }
[ -f "$W/separate_done" ] || { step separate; python -m training.moises_data separate "$W" >> "$W/separate.log" 2>&1 || fail separate; touch "$W/separate_done"; }
[ -f "$W/segments_done" ] || { step segments; rm -rf "$W/data"; python -m training.moises_data segments "$W" "$W/data" >> "$W/segments.log" 2>&1 || fail segments; touch "$W/segments_done"; }
for split in val test; do for sep in sw demucs; do
  [ -d "$W/items_${split}_$sep" ] || python -m training.moises_data items "$W" $split $sep "$W/items_${split}_$sep" >> "$W/items.log" 2>&1 || fail items
done; done
step "data ready: $(ls "$W/data" | wc -l) segments"
[ -f "$W/val_released.json" ] || python -m benchmarks.fullband.thresholds released --data "$W/items_val_sw" --out "$W/val_released.json" > "$W/val_released.log" 2>&1 &
if [ ! -f "$W/train_done" ]; then
  last=$(ls "$W/runs" 2>/dev/null | sed -n 's/^step_\([0-9]*\)\.pth$/\1/p' | sort -n | tail -1)
  resume=(); [ -n "$last" ] && resume=(--init "$W/runs/step_$last.pth" --start "$last")
  step "train from ${last:-0}"
  OMP_NUM_THREADS=6 python -m training.finetune_riley --data "$W/data" --out "$W/runs" --steps "$STEPS" --every "$EVERY" \
    --batch 16 --workers 6 "${resume[@]}" >> "$W/train.log" 2>&1 || fail train
  touch "$W/train_done"
fi
wait
step train_done
for c in "$W"/runs/step_*.pth; do
  s=$(basename "$c" .pth)
  [ -f "$W/val_$s.json" ] || FRETWORK_RILEY_CHECKPOINT="$c" python -m benchmarks.fullband.thresholds "$s" --data "$W/items_val_sw" --out "$W/val_$s.json" > "$W/val_$s.log" 2>&1
done
step DONE
