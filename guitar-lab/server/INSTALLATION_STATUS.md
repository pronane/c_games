# Separation installation status — 2026-10-31

## Installed and checked in this sandbox

- Python 3.11 virtual environment (ignored; recreate after a snapshot if absent).
- PyTorch **2.2.2+cu121** and torchaudio **2.2.2+cu121**: both import successfully.
- Demucs **4.0.1** and its dependencies installed.
- Basic Pitch **0.4.0** with real ONNX transcription functioning.
- `torch.cuda.is_available()` is **false**. This machine will use CPU; CUDA libraries in the wheel do not mean a GPU is present.

## Checkpoint still not installed

Required file: `5c90dfd2-34c22ccb.th`, **54,996,327 bytes**.

Expected SHA-256:

```
34c22ccb381c6f9fdbf324f04e1e2fe21aaaf293f5ded163a162697ff9a02ddd
```

The public GitHub release mirror was located, but its download redirects to `release-assets.githubusercontent.com`, outside this sandbox's allowed outbound hosts. The primary publisher's host is also outside the allowed list. GitHub repository copies accessible through the API returned **133-byte Git LFS pointers**, not model weights; these were rejected and removed. No network filter was bypassed. No fake/other stem is used.

A real six-source separation inference test therefore **has not run**. Full-band submissions remain gated until the exact verified checkpoint is supplied.

## Finish installation

Open this link **in your own browser** (the server's egress policy does not apply to your browser):

https://github.com/nomadkaraoke/python-audio-separator/releases/download/model-configs/5c90dfd2-34c22ccb.th

Either:

1. In the studio's **Specialist Audio Engine → One-time guitar model setup**, choose **Install downloaded checkpoint**. This operator-only development feature must be enabled with `FRETWORK_ALLOW_MODEL_INSTALL=1` when launching the API. The server validates the exact length and full SHA-256, then atomically installs the weights and fixed model definition.
2. Place the downloaded file on the server and run:

```sh
cd guitar-lab
.venv/bin/python -m server.model_store --checkpoint /path/to/5c90dfd2-34c22ccb.th
.venv/bin/python -m server.model_store --check
FRETWORK_RUN_SEPARATION_TEST=1 .venv/bin/python -m pytest server/tests/test_transcription_integration.py -q
```

On a server without restricted egress, `.venv/bin/python -m server.model_store` downloads and verifies the pinned checkpoint automatically. It is an operator action, never triggered by an audio upload.

The default model cache is `guitar-lab/.cache/models/demucs`, excluded from Git/snapshots along with virtual environments. Set `FRETWORK_DEMUCS_REPO` to provisioned persistent model storage in a real deployment. No server restart is needed after checkpoint installation; refresh engine availability in the studio.
