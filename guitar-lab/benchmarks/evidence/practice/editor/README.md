# Visual editor / reference retention / progress follow-up

Follow-up on PR #92, based on 4b98bbe plus these changes. This directory supplements rather than replaces the original practice-workflow evidence.

- `build.txt`: production TypeScript/Vite build after clean `npm ci`.
- `frontend.txt`: frontend unit tests, including six visual editing/history tests and two additional project attachment/progress tests.
- `browser.txt`: real Chromium with a synthetic project fixture. Tests chord selection, numeric and keyboard pitch/time/length changes, pointer drag, add/delete, undo/redo, audition, explicit apply/revision/approval invalidation, historical-take guard, coverage-gated progress and original-chart byte-for-byte export/import/IndexedDB reload.
- `practice-browser.txt`: original fake-microphone/mocked-comparison workflow rerun as a regression test.

The editor browser test does not call a real transcription model. The practice regression still uses mocked comparisons. These results do not measure real-guitar accuracy or constitute independent human validation.

No Python/backend code changed in this follow-up; Python tests were not rerun here. The earlier 24-test targeted Python result remains in the parent directory as historical evidence for the original PR implementation. No model inference, GPU or physical USB testing was performed. Temporary Chromium/runtime libraries were provided outside Git; no browser/dependency files or private recordings are included.
