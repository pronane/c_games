# Held-out quiet/wet and human sustain milestone

Implementation: `5cdb730` on `arena/23399fc5-c-games`. No merge performed.

## Completed

- A versioned collection protocol, frozen before acquiring the new evaluation data.
- Strict audio/label checksum checks, local path containment, known-development exclusions, parent-source grouping, duplicate/overlap rejection, human-review declarations and coverage gates.
- A paired Riley baseline/guard evaluator with onset/pitch F1, conditional offset errors, raw sustain false-warning/miss counts and unmatched coverage. It cannot improve a score merely by changing review wording. Condition/label truth is never passed into inference. It restores the guard environment flag even after errors.
- Source-grouped summaries and bootstrap infrastructure; no variants counted as independent performances.
- A local browser review page with audio playback, manual note/direct-offset entry, expected-duration/reference judgements, checksum-linked JSON export and explicit personal-review confirmation. No audio upload endpoint.
- Three ten-second review windows prepared from the user's existing take (0, 145 and 290 s), with pending-label templates, timestamps and the review page in a private ZIP. No notes, dry/wet categories or sustain judgements were inferred. This is **development review material**, not independent holdout data.

## What remains blocked

**There are zero approved independent clips and zero completed human sustain labels.**

`intake-status.json` is a fresh real coverage audit, not reconstructed prior evidence. The `evaluate` command returned exit **3**, `inference_run: false`, `quality_approved: false`. No Riley inference or new accuracy measurement was performed.

The initial requirement is six independent physical performances from at least three new performers, paired across dry/quiet-dry/real-wet/quiet-wet conditions, plus 20 correct, 20 short and 10 long human sustain examples across at least three source performances. Real effect capture and digital level variants must be distinguished from synthetic room simulations. Parent recordings and human labels must be supplied before this stage can produce meaningful accuracy results.

Known project development recordings remain excluded. The model's original training overlap is unknown; “held out” refers to this project's tuning. Human review is declared, not identity-authenticated by a checkbox.

## Fresh verification

| Check | Result | Artifact |
|---|---|---|
| New intake/evaluator unit tests | **37 passed** | `tests.txt` |
| Human-review UI browser smoke | PASS | `review-browser.txt` |
| Existing frontend production build | PASS | `frontend.txt` |
| Existing frontend unit tests | **53 passed** | `frontend.txt` |
| Actual holdout evaluate command | **BLOCKED, exit 3**, no inference | `intake-status.json`, `intake-exit.txt` |
| Private listening-packet preparation | Three windows, review pending | `packet-preparation.txt`, `review-packet-status.json` |

The 37 tests use synthetic schema fixtures and mocked inference to verify validation, flag restoration, raw metric bookkeeping and refusal behaviour. They are not human-labelled recordings and not neural-model quality evidence. The browser test simulates a reviewer on a synthetic tone, checks required fields/checksum/export/no-upload/mobile behaviour, then deletes the exported fixture. It is explicitly **not human review**.

The previous full-app Python and Riley/browser results remain in `../routing/`; that full suite and real neural inference were not rerun in this infrastructure-only follow-up. No existing engine policy, notation/fingering algorithm or app default was changed.

## Reproduce / continue

From guitar-lab:

```sh
python -m pytest server/tests/test_holdout.py -q
python -m benchmarks.holdout evaluate --manifest benchmarks/holdout/intake.json --out /tmp/holdout-status.json
# Exit 3 is expected while the checked-in intake is empty.
python -m benchmarks.holdout.serve_review --port 8765
# Separate terminal; local compatible Chromium required:
BROWSER_EXECUTABLE_PATH=/local/chromium npm run test:review
```

Review instructions and manifest schema: [holdout README](../../holdout/README.md). Supply independent recordings and exported human labels privately; do not put audio/model weights in Git. The prepared ZIP is local at `benchmarks/regression/data/private/user/sustain-review.zip` and is intentionally not pushed. Reviewers can open its `review.html` or use the live review page, selecting the downloaded window WAV locally. The file packet currently contains pending labels only.

No gate is a merge approval. Both engine experiment flags remain OFF by default.
