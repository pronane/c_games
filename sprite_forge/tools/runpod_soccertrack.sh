#!/bin/sh
# SoccerTrack v2 -> Sprite Forge moves on a GPU pod (v11.29).
#   HF_TOKEN=hf_... sh tools/runpod_soccertrack.sh WORK [WORKERS] [MATCH ...]
# The dataset is CC BY 4.0 but gated on Hugging Face: the token's account must have accepted its terms.
# Downloads videos + labels + boxes (~145 GB), cuts every labelled event, merges into WORK/out/moves,
# then keeps only the takes that pass Arena FC's checks in WORK/stage (small enough to bring back).
set -e
HERE=$(cd "$(dirname "$0")/.." && pwd)
WORK=$1; shift; WORKERS=${1:-6}; [ $# -gt 0 ] && shift
mkdir -p "$WORK/data" "$WORK/out" "$WORK/models"
python3 -m pip install -q "onnxruntime-gpu==1.22.*" opencv-python-headless numpy scipy ijson huggingface_hub
python3 "$HERE/tools/fetch_models.py" --dir "$WORK/models" rtmpose_l_halpe26
cp "$HERE/sforge/models/lifter_v1.onnx" "$HERE/sforge/models/lifter_v1.json" "$HERE/sforge/models/registry.json" "$WORK/models/"
PATTERNS='["bas/*","gsr/*","videos/*"]'
if [ $# -gt 0 ]; then PATTERNS=$(python3 -c "import json,sys; print(json.dumps([p % m for m in sys.argv[1:] for p in ('bas/%s/*','gsr/%s/*','videos/%s/*')]))" "$@"); fi
python3 - "$WORK/data" "$PATTERNS" <<'PY'
import json, os, sys
from huggingface_hub import snapshot_download
snapshot_download("atomscott/soccertrack-v2", repo_type="dataset", local_dir=sys.argv[1],
                  allow_patterns=json.loads(sys.argv[2]), token=os.environ["HF_TOKEN"], max_workers=16)
PY
if [ $# -gt 0 ]; then
  python3 "$HERE/tools/soccertrack_capture.py" "$WORK/data" "$WORK/out" --models "$WORK/models" --workers "$WORKERS" --matches "$@"
else
  python3 "$HERE/tools/soccertrack_capture.py" "$WORK/data" "$WORK/out" --models "$WORK/models" --workers "$WORKERS"
fi
python3 "$HERE/../arena-fc/Tools/import_matchcapture.py" --source soccertrack "$WORK/out/moves" --stage "$WORK/stage"
