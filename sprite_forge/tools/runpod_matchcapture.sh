#!/bin/sh
# Batch job for a GPU pod (RunPod or any CUDA box): match video -> Sprite Forge moves.
#   sh tools/runpod_matchcapture.sh FOOTAGE_DIR OUT_DIR [WORKERS]
set -e
HERE=$(cd "$(dirname "$0")/.." && pwd)
OUT=$2; mkdir -p "$OUT/models"
python3 -m pip install -q onnxruntime-gpu opencv-python-headless numpy
python3 "$HERE/tools/fetch_models.py" --dir "$OUT/models" yolox_m_humanart rtmpose_l_halpe26
cp "$HERE/sforge/models/lifter_v1.onnx" "$HERE/sforge/models/lifter_v1.json" "$HERE/sforge/models/registry.json" "$OUT/models/"
python3 "$HERE/tools/matchcapture_batch.py" "$1" "$OUT" --workers "${3:-6}"
