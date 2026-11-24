# Ball / controlled-player framing

Gameplay camera views and set shots retain their normal tracking and easing. A final framing correction checks ball and controlled-player centres against NDC ±0.78, recentres on a ball-weighted centroid when necessary, and pulls back enough to fit both. The solve includes each subject's perspective depth, not just their lateral spread. Attract mode frames only the ball. Celebration orbits remain cinematic and exempt.

This is a centre-point framing constraint, not an occlusion test or a guarantee of readable subject size when the player and ball are far apart. Manual browser review is still required for camera feel, zoom pumping, occlusion, and GPU performance.

## Verification

- Pure tests: projection, behind-camera rejection, no-op, portrait/wide aspects, deterministic spread/depth cases and vertical/degenerate views.
- Camera integration test: all five gameplay views plus set shots; ball/player jumps, portrait and landscape, corrected after easing.
- Local `node scripts/check.mjs`: TypeScript, tests, production build and asset contracts.
- Motion A/B workflow: experimental SwiftShader capture logs `AB_CAMSTAT` into **console.log** (electron.log is process diagnostics). The summary and sticky PR comment show observed visibility. `check_framing.mjs` fails the experimental job on absent samples, visibility below 100%, or a peak outside ±0.78. The job remains non-blocking.
- The existing attract capture exercises **ball only**. Player n/a is explicitly not player coverage. In-match player tracking has automated integration coverage, not captured visual sign-off.

Workflow edits must be pushed before GitHub can run them. No remote workflow success or human GPU review is implied by passing local checks.
