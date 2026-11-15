# Guided practice verification

Evidence for the Review → Practise → Retry feature, based on e703f9a plus this PR's changes.

- `build.txt`: production TypeScript/Vite build PASS after clean `npm ci`.
- `frontend.txt`: 59 frontend tests PASS, including six new project/helper tests.
- `python.txt`: 24 targeted comparison/transcription-check tests PASS. Synthetic notes/audio, mocked model/API paths; not an inference benchmark.
- `browser.txt`: actual Chromium workflow PASS with fake microphone and mocked comparison response; no browser exceptions. Covers chart entry, unreviewed and excluded grading gates, recording, evidence listening, human review, focus/retry, IndexedDB reload with audio, portable audio/review export, reference correction and deletion.

Browser run used a temporary npm-distributed Chromium with its runtime libraries (`LD_LIBRARY_PATH=/tmp/al2023/lib`, `BROWSER_EXECUTABLE_PATH=/tmp/chromium`). Browser binaries, dependencies and generated audio are not committed. The committed browser test supports a separately installed Chromium via `BROWSER_EXECUTABLE_PATH`.

No full Python suite, real-model inference benchmark, GPU/physical USB test, real-user study or independent accuracy validation was performed for this feature. The validation protocol and explicit pending-human-evidence boundary are in `PRACTICE_WORKFLOW.md`. No new model weights, datasets or private audio are included.
