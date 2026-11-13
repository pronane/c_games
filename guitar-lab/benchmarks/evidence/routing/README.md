# Routing follow-up: fresh verification

Tested implementation: `2f084ec`, following the paired evidence at `../README.md`.

## Fixes

- `/api/compare` accepts a `transcriber` form field, validates the selected installed backend, passes it to `transcribe_take`, and labels that same backend. An omitted field uses the engine default.
- Tab comparison and song-take clients send the shared browser selection.
- Song-take API uses the explicit selection, or its song session's backend when omitted. It no longer implicitly uses an unrelated server default.
- Jobs label their explicit backend correctly. Older score-informed tab jobs still intentionally use Basic Pitch posterior maps and preserve that provenance; this is not converted into a Riley score-informed algorithm.
- Regression tests cover explicit/default routing, labels, rejection without inference, session-vs-global selection and multipart client fields.

## Results

| Check | Result | Log |
|---|---|---|
| Build + frontend unit | PASS / 53 passed | `frontend.txt` |
| Comparison Python tests (targeted) | 19 passed | `compare.txt` |
| Entire Python suite, flags OFF | 206 passed, 3 skipped | `python_flags_0.txt` |
| Entire Python suite, flags ON | 206 passed, 3 skipped | `python_flags_1.txt` |
| E2E browser | PASS | `e2e.txt` |
| Input browser simulation | PASS | `inputs.txt` |
| Profile browser | PASS | `profiles.txt` |
| Tab browser | PASS | `tab.txt` |
| Default Riley + explicit Basic Pitch browser/API | PASS | `riley.txt` |

Per-command exit codes are in `python_status.txt` and `browser_status.txt`. These matter: the loop wrapper can return zero despite a failed command. All listed commands returned zero in this follow-up.

Skipped Python coverage: EGSet12/Guitar-TECHS absent, opt-in heavy separator unavailable, older private AAC fixtures absent. Full-band song browser check was not rerun: health confirms the separator remains unconfigured (`health.json`). Do not count that as a pass. Existing earlier blocked/failing logs remain in the parent directory for provenance.

Tab microphone fixture now uses a bundled real GuitarSet WAV by default, rather than a beep. The recording intentionally does NOT match the chart. Assertions exercise capture, detected-note replay, notation rendering/export option and layout—not musical correctness. No reference notes are inserted into the take prediction. The score-informed check in this older path uses Basic Pitch regardless of optional detector selection, as documented in its provenance.

The real-guitar browser check independently verifies fresh default Riley selection and actual inference (102 notes), then explicit Basic Pitch override (98 notes), each HTTP 200 with the correct label and no browser JavaScript errors. **Different counts do not establish better accuracy.** It sends the explicit form selection to the real endpoint; client multipart wiring is also tested separately.

## Environment and scope

`environment.txt` records Python packages. CPU torch/ONNX, local trusted-model tensor copy reconstructed and strictly checked from the user's uploaded archive parts, ffmpeg available. This evaluation environment is not a proposed production security/dependency lock. A local npm-distributed Chromium and its bundled shared libraries were used; browser tests require a compatible local executable.

Experimental flags were enabled in the preview/browser engine, tested OFF and ON in Python, and remain OFF by default in source. No inference thresholds, model architecture, score quantisation or string/fret algorithm was changed in this follow-up. Earlier accuracy experiments were not rerun as a new larger-library study. Uploaded AAC windows were not re-transcribed in this routing follow-up.

## Reproduction

From guitar-lab, with dependencies, ffmpeg, local Riley checkpoint and compatible Chromium installed:

```sh
export FRETWORK_RILEY_CHECKPOINT=/local/trusted-checkpoint.pth
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2
FRETWORK_RILEY_LEVEL_GUARD=0 FRETWORK_DURATION_REVIEW=0 python -m pytest server/tests -q -ra
FRETWORK_RILEY_LEVEL_GUARD=1 FRETWORK_DURATION_REVIEW=1 python -m pytest server/tests -q -ra
npm run build && npm test
# Start engine and frontend separately; set BROWSER_EXECUTABLE_PATH/library paths.
npm run test:e2e
npm run test:inputs
npm run test:profiles
npm run test:tab
npm run test:riley
```

No merge performed. See `../../../BRANCH_STATUS.md` for the complete branch-level completed/outstanding breakdown.
