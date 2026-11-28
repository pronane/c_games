# Ball / controlled-player framing

> **Current policy:** see `GAMEPLAY_RECOVERY.md`. The gameplay review supersedes the original always-fit-both requirement below. The camera now prioritises the live ball, plans nearby selection before easing, holds pullback distance, and uses the existing edge arrow for distant selection. The historical guarantee/test description below describes the first implementation, not current visual acceptance.

Gameplay camera views and set shots retain their normal tracking and easing. A final framing correction checks ball and controlled-player centres against NDC ±0.78, recentres on a ball-weighted centroid when necessary, and pulls back enough to fit both. The solve includes each subject's perspective depth, not just their lateral spread. Attract mode frames only the ball. Celebration orbits remain cinematic and exempt.

This is a centre-point framing constraint, not an occlusion test or a guarantee of readable subject size when the player and ball are far apart. Manual browser review is still required for camera feel, zoom pumping, occlusion, and GPU performance.

## Verification

- Pure tests: projection, behind-camera rejection, no-op, portrait/wide aspects, deterministic spread/depth cases and vertical/degenerate views.
- Camera integration test: all five gameplay views plus set shots; ball/player jumps, portrait and landscape, corrected after easing.
- Local `node scripts/check.mjs`: TypeScript, tests, production build and asset contracts.
- Motion A/B workflow: experimental SwiftShader capture logs `AB_CAMSTAT` into **console.log** (electron.log is process diagnostics). The summary and sticky PR comment show observed visibility. `check_framing.mjs` fails the experimental job on absent samples, visibility below 100%, or a peak outside ±0.78. The job remains non-blocking.
- Attract captures exercise **ball only**. A third `match` leg uses `?ab=1&scenario=match`, a fixed seed, the LOD candidate, and a live controlled player with neutral input. This exercises real match/camera code but is not scripted human movement or exhaustive gameplay coverage. Its check requires observed player samples; n/a fails rather than silently passing.
- Visibility is emitted every two seconds even on very slow software renderers (previously it required 30 frames per sample). Hidden-window background throttling is disabled for capture. Both are capture robustness improvements, not a confirmed diagnosis of the earlier failure.
- The checker requires at least two samples per log and emits GitHub error annotations containing failing values or missing-sample diagnostics. All three legs are included in summaries, video assembly and artifacts.

Workflow edits must be pushed before GitHub can run them. No remote workflow success or human GPU review is implied by passing local checks.

## Follow-up of PR #266

GitHub run `45385258534` (PR) and run `45386185166` (post-merge) had successful `ab-metrics` jobs but failed experimental `visual-ab` jobs. The PR run completed both attract captures and MP4 assembly; the camera visibility check failed. A green overall workflow is **not** proof that this non-blocking job passed.

Detailed logs/video could not be fetched in this environment: GitHub redirected downloads to an artifact host outside the available network access. No captured video has been visually reviewed here, and the cause of the framing-check failure is not yet confirmed. The new match leg and diagnostics need a fresh workflow run after these changes are pushed; no success is claimed in advance.
