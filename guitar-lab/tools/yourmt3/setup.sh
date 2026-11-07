#!/usr/bin/env bash
# Optional: set up YourMT3+ for benchmarking (about 3 GB with PyTorch). Not used by default.
# Usage: tools/yourmt3/setup.sh [target-dir]   then export the two variables it prints.
set -euo pipefail
dir="${1:-$HOME/yourmt3}"
mkdir -p "$dir"
[ -d "$dir/code" ] || GIT_LFS_SKIP_SMUDGE=1 git clone --depth 1 https://huggingface.co/spaces/mimbres/YourMT3 "$dir/code"
[ -x "$dir/venv/bin/python" ] || python3 -m venv "$dir/venv"
"$dir/venv/bin/pip" install -q torch torchaudio --index-url https://download.pytorch.org/whl/cpu
"$dir/venv/bin/pip" install -q "lightning>=2.2.1" deprecated librosa einops transformers==4.45.1 numpy==1.26.4 mido mir_eval soundfile huggingface_hub wandb
"$dir/venv/bin/python" - "$dir/code/amt" <<'PY'
import sys
from huggingface_hub import hf_hub_download
hf_hub_download('mimbres/YourMT3', 'logs/2024/mc13_256_g4_all_v7_mt3f_sqr_rms_moe_wf4_n8k2_silu_rope_rp_b36_nops/checkpoints/last.ckpt', local_dir=sys.argv[1])
PY
echo "export FRETWORK_YOURMT3_ROOT=$dir/code"
echo "export FRETWORK_YOURMT3_PYTHON=$dir/venv/bin/python"
