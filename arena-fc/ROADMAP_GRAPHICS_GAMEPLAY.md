# Arena FC — Graphics, Gameplay and Product Roadmap

This is the active roadmap for closing the gap to a full football game on the
level of EA SPORTS FC and eFootball. Licensing and use of protected player or
stadium identities are out of scope; the target is original content with
competitive visual, gameplay, and mode depth.

The roadmap prioritizes match feel, player realism, and visual quality before
broadening modes. A feature is not complete because a class, menu item, or
placeholder exists: each phase needs an in-game path, focused tests, and an
observable acceptance result.

## Principles

- **Gameplay first, graphics in service of readability.** The ball, controlled
  player, contact point, and next action must remain easy to read.
- **Original assets only.** Improve anatomy, faces, kits, motion, and stadiums
  without copying identifiable real-world players, teams, or venues.
- **Keep simulation deterministic.** Rendering, animation, and visual effects
  must not change match outcomes or network-authoritative state.
- **Make quality scalable.** Maintain a broad-compatibility GPU profile and
  higher-fidelity GPU profiles, with measured budgets on named hardware. Keep
  software CPU rendering optional unless it meets a useful playability budget.
- **Separate Sprite Forge work.** Any Sprite Forge source enhancement gets its
  own independent PR, separate from Arena FC runtime/integration PRs. Arena FC
  can consume the resulting assets or tools in a separate integration change.
- **No false completion.** Each milestone must meet its exit criteria and pass
  its relevant test/build checks before being marked complete.

## Platform target strategy

The older Intel laptop is a legacy compatibility and stress-test reference,
not the desired target tier. Define the minimum separately, using measurements
from representative target devices. No newer target machine is currently
available, so minimum specifications and performance budgets remain open;
do not infer them from the laptop's results.

- **Windows and Linux desktop:** first reference targets, using the GPU. Use
  Godot Compatibility for broad hardware coverage, Mobile for phones/tablets
  and compatible performance-conscious devices, and Forward+ for higher-end
  desktop visuals.
- **Phones and tablets:** use GPU rendering with mobile-specific quality,
  memory, thermal, battery, and touch-control budgets. Do not assume the
  desktop renderer or settings are appropriate.
- **Browser:** use the Compatibility renderer; it is Godot's web renderer.
  Arena FC currently has a separate GDScript browser runtime because the
  upstream C#/.NET project cannot be exported to web. Its match rules and
  feature parity must be measured and managed explicitly.
- **Consoles:** a later porting workstream, after the game and platform
  boundaries are stable. Allow for platform access, development kits, porting
  support, and certification rather than treating console builds as a routine
  export.
- **True CPU software rendering:** an optional Windows/Linux desktop fallback,
  only if a named target machine can run it reliably at an acceptable frame
  rate. It is not the normal renderer across platforms.

Godot's renderer choices and platform support differ; see the
[Godot 4.7 renderer overview](https://docs.godotengine.org/en/4.7/tutorials/rendering/renderers.html).
The gameplay, animation, player-asset, and readability work in Phases 1–4 is
not blocked on enhanced GPU rendering. Keep those changes working on
Compatibility and defer renderer-specific effects to Phase 5.

### Recommended delivery order

1. Establish a GPU-rendered Windows desktop reference build and a representative
   target PC; bring Linux desktop to the same functional/performance baseline.
2. Validate the existing browser edition's feature parity and performance,
   while developing separate mobile GPU, touch, memory, and thermal profiles.
3. Address consoles after the PC/mobile architecture, controls, saves, and
   online services are ready for a platform-specific port.

## Current evidence

The review of the current `main` build found:

- The game uses Godot's **GL Compatibility** renderer globally. That renderer
  still renders on a GPU; it is not a CPU software renderer.
- `ForwardPlusConfig.Apply` contains enhanced-renderer settings, but no current
  call site was found. The project therefore does not yet offer a verified
  switchable baseline/enhanced renderer path.
- The developer machine is an Intel Core i7-8550U (4 cores / 8 threads),
  32 GB RAM, and Intel UHD Graphics 620 with 1 GB reported graphics memory. It
  is now treated as a legacy compatibility reference, not target hardware.
- A non-headless 5v5 Compatibility-renderer profile on this machine measured
  42.3 average FPS, 23.63 ms average frame time, and 26.32 ms p95 over 120
  frames after a 60-frame warm-up. It reported about 423 draw calls and 630k
  primitives per frame. This is a Debug/development build at the project's
  1280x720 window size on a 1920x1080 display, not a release-build target.
- Godot 4.7 also enumerates Windows' **Microsoft Basic Render Driver** as a
  CPU device when using the D3D12 Forward+ renderer. This is the first
  candidate for the requested software-rendered profile. A 5v5 Debug profile
  at 1280x720 completed once at 7.5 average FPS (133.47 ms average frame,
  148.74 ms p95, 150.00 ms p99; 438 draw calls and 625k primitives). A repeat
  launch became unresponsive before completing and had to be terminated, so
  this route is not yet a reliable playable profile. Check availability on
  other PCs before committing to it.
- The match loads one shared generated footballer model and varies some
  appearance through material tint and scale. The pipeline already includes
  rigging and many motion clips, so animation work should begin with measured
  in-game defects rather than assuming those systems are absent.
- The browser edition has its own GDScript match runtime; it is not simply the
  C# desktop build exported to a browser. Keep its behavior in the parity
  checklist.
- The HUD has a duplicate score display and optional overlays whose parent
  panels remain visible when their labels are hidden.
- Several modes and systems exist only partially: practice/drill behavior,
  career persistence and squad integration, playable replay reconstruction,
  and server-backed ranked matchmaking need completion.

## Phases

### Phase 0 — Baseline, capture and quality targets

**Goal:** make visual and gameplay improvements measurable and repeatable.

- Establish fixed-seed match scenes and repeatable captures at representative
  broadcast and close-up cameras.
- Record current frame time, rendering backend, draw calls, player/ball
  visibility, and frame-time spikes on the minimum and target hardware.
- Use `godot --path . -- --arena-profile-frames 120` for a 60-frame warm-up
  followed by a 120-frame live 5v5 profile. Do not use `--headless` for renderer
  measurements; it does not display the real renderer.
- Define minimum hardware and acceptance budgets before promising 60 FPS or a
  particular resolution. Use the older laptop as a compatibility/stress
  reference, not the desired target tier.
- Add representative Windows/Linux desktop, phone/tablet, and browser targets
  to the validation matrix; defer console targets until platform access and a
  porting path exist.
- Keep a before/after image and gameplay capture for each visual milestone.

**Exit:** a documented test setup with named hardware, reliable reproduction,
and measurable baseline budgets.

### Phase 1 — Match readability and presentation cleanup

**Goal:** remove obvious presentation defects and make play easy to follow.

- Remove duplicate score graphics and ensure inactive overlay panels are hidden.
- Tune broadcast camera framing, zoom, pitch coverage, and ball/player scale.
- Improve active-player, ball, and opponent indicators without covering play.
- Balance HUD density, contrast, safe areas, and touch/controller layouts.
- Keep the commentary feed, minimap, and action hints from overlapping; hide
  the minimap while touch controls are active.
- Review pitch color, exposure, shadow softness, and crowd contrast in actual
  gameplay captures.

**Exit:** no duplicated or empty HUD panels; the ball and controlled player are
consistently identifiable at the supported gameplay resolutions.

**Status:** Desktop Compatibility pass complete at 1280x720. Mobile/tablet and
browser safe-area validation remains open until representative devices are
available.

### Phase 2 — Football feel and animation/gameplay synchronization

**Goal:** make movement, touch, passing, shooting, defending, and goalkeeping
feel intentional and physically coherent.

- Measure and tune acceleration, deceleration, turning, sprinting, and
  directional transitions against simulation movement.
- Improve first touch, ball trapping, dribble separation, pass/shot contact,
  rebounds, tackles, and goalkeeper decisions.
- Audit clip selection, crossfades, phase matching, foot planting, and foot-to-
  ball contact in the built game; fix visibly mistimed or sliding motion.
- Add repeatable scenarios for turns, sprint stops, passes, shots, tackles,
  keeper saves, and recovery animations.
- Preserve fixed-step determinism and ensure presentation changes cannot alter
  the authoritative simulation.

**Exit:** focused gameplay scenarios pass, input-to-action timing is measured,
and no known high-frequency action has visibly broken contact or locomotion.

**Progress:** one-shot imported clips now start at frame zero and derive playback
speed from the authored contact fraction and simulation contact time. Procedural
fallback action poses use the same contact timing. Core regression tests pass;
in-engine visual verification is still outstanding.

### Phase 3 — Original lifelike player pipeline

**Goal:** raise player quality substantially beyond the current generic shared
model while keeping performance and customization practical.

- Improve body proportions, silhouette, face/head detail, hair, boots, and
  uniform construction with original designs.
- Add authored variation for height, build, skin, hair, and role without making
  each player require a unique heavy mesh.
- Improve UVs, texture detail, physically based material response, skin/cloth
  shading, and kit-number placement.
- Validate skin weights, deformation at joints, clip retargeting, and close-up
  quality in both editor and match camera.
- Keep asset generation reproducible and include asset-level checks and
  budgets.

**PR boundary:** changes to Sprite Forge itself are separate independent PRs.
Arena FC changes that consume the improved pipeline or generated assets remain
separate integration PRs; do not combine both codebases' work in one PR.

**Exit:** original player assets pass close-up and gameplay-distance review,
deform cleanly in representative animations, and fit the defined asset budget.

### Phase 4 — Stadium, lighting, turf and atmosphere

**Goal:** replace the current procedural/blocky presentation with coherent,
believable original match environments.

- Improve turf shading, markings, wear, surface response, and ball contact
  readability.
- Add varied original stands, crowd silhouettes/animation, banners, goals, and
  contextual stadium detail.
- Improve day/night lighting, shadows, exposure, weather presentation, and
  post-processing while retaining a readable ball and kit colors.
- Make crowd and stadium reactions follow match events without affecting sim
  state.

**Exit:** representative stadium captures meet the agreed visual target and
remain within the relevant performance profile.

### Phase 5 — Switchable scalable rendering

**Goal:** provide scalable, platform-appropriate GPU rendering, with an
optional true CPU software-rendered desktop fallback if it proves viable.

- Keep true software CPU rendering distinct from Godot Compatibility, which
  still uses a GPU. Evaluate the Windows software-driver route for a desktop
  fallback only; do not make it the default or promise it across platforms.
- The current Windows test confirms the Microsoft Basic Render Driver can
  render a match, but its 7.5 FPS result misses a practical gameplay target
  and a repeat launch hung. Treat it as proof of availability only; validate
  any CPU fallback on named supported hardware before exposing it to players.
- Compare Compatibility, Mobile, and Forward+ on the platforms where each is
  supported; verify that assets and effects behave consistently.
- Define GPU profiles for browser/low-end, mobile/tablet, and desktop hardware,
  with separate crowd, lighting, shadows, antialiasing, post-processing,
  memory, and frame-time budgets.
- Keep the CPU software fallback only if it passes reliability and frame-time
  targets on a named supported desktop configuration; otherwise omit it from
  release builds rather than silently substituting another renderer.
- Persist the choice and make renderer changes take effect at startup/restart
  when Godot requires it; report unsupported choices rather than silently
  falling back.
- Profile memory, loading time, frame time, and thermal behavior.

**Exit:** every shipped profile launches reliably on its target hardware, with
tested switching/persistence and documented performance budgets.

### Phase 6 — Complete the football modes and progression

**Goal:** make the advertised game modes operational and mutually distinct.

- Implement objective-based training and skill drills plus a real free-practice
  arena.
- Complete career save/load, seasons, transfers, player progression, and
  connection of career squads to match setup.
- Make tournaments advance fixtures, retain results, and reach a final.
- Record and reconstruct playable match-state replays; add a usable replay
  theatre and highlights workflow.
- Correct ranked-result calculations, including fair draw scoring, and keep
  local test matchmaking clearly distinguished from online ranking.

**Exit:** mode-specific end-to-end flows survive save/reload and have focused
regression tests.

### Phase 7 — Online competition and social depth

**Goal:** progress from friend-room matches to reliable competitive services.

- Add server-backed matchmaking, ranking, seasonal divisions, reconnect
  handling, and match-result validation.
- Add spectator and co-op/team modes only with clear authority, latency, and
  abuse protections.
- Test online simulation under latency, packet loss, disconnect, and
  rejoin/host failure.
- Separate prototype/local modes from live competitive modes in the UI.

**Exit:** end-to-end online competitive sessions pass automated network
scenarios and operational monitoring requirements.

### Phase 8 — Product readiness and parity

**Goal:** close remaining breadth gaps and support a reliable release.

- Audit tactics, set pieces, referee/injury/substitution systems, accessibility,
  localization, onboarding, control remapping, and platform parity.
- Define original content cadence and progression systems without copying
  protected teams, players, or stadiums.
- Establish save migration, crash diagnostics, performance regression checks,
  release packaging, and platform certification requirements.
- Re-run the feature-by-feature gap analysis against current FC/eFootball
  releases before release planning.

**Exit:** every advertised feature is implemented and tested, with known
limitations explicit and release performance stable on supported hardware.

## Implementation progress

The first Arena FC-only visual change removes the duplicate score bug and hides
the lower-third/stats panel containers until their content is shown. The next
HUD fix separates the commentary/minimap panels from the action hints and hides
the minimap while touch controls are active; an optional FPS readout is
available from F3 or the pause menu. The default broadcast camera is closer,
the pitch color is less saturated, and the pressure ring no longer duplicates
the opponent ball-carrier marker. These changes do not depend on Sprite Forge
or enhanced GPU rendering. The 1280x720 live-play capture and focused tests
passed. Phase 2 gameplay/animation synchronization is now the next workstream.

## Open decisions

- Which specific desktop, mobile/tablet, and browser devices define minimum
  and target performance budgets?
- Should the browser edition retain its separate GDScript match runtime, or
  should simulation sharing/parity be a dedicated architecture milestone?
