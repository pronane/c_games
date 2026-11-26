# Arena FC CI testing guide

## Why this exists

The Arena AI editing sandbox may not have Godot or .NET installed. GitHub Actions is the independent execution environment: it installs .NET 9 and Godot 4.7.2 Mono, builds the project, runs existing suites, exercises deterministic simulations, collects .NET coverage and renders screenshot artifacts.

A local agent must never describe a build, runtime test or rendered capture as successful unless the matching workflow ran on the commit being reported.

## Workflows

### Existing: Arena FC tests

`.github/workflows/arena-fc-tests.yml` remains the primary build/regression workflow. It covers the Godot C# build, server build, pure-C# suites, Godot headless self-test, GDScript checks and Node/network smoke tests.

### Added: Arena FC quality gates

`.github/workflows/arena-fc-quality.yml` adds:

- **Asset and Python contracts:** Python syntax compilation and schema-aware validation of both v1 and v2 clip manifests. The v2 checks cover normalized left/right plant curves, paired 32-sample phase curves, 64 finite X/Z root-velocity samples, contact windows, source/provenance consistency and the GLB header/declared length.
- **Seeded simulation stress:** paired identical-seed 5v5, 7v7 and 11v11 matches; compares authoritative state each tick and rejects non-finite player/ball state.
- **.NET coverage reports:** collects Cobertura reports from the existing CoreTests and MatchCoreTests console test runners using Microsoft's cross-platform `dotnet-coverage`.
- **Rendered evidence:** uses Xvfb and Mesa software rendering to execute the existing procedural-rig and browser-game screenshot scripts. PNGs are uploaded as workflow artifacts.

Pull-request stress runs use 3 seeds and 30 simulated seconds per team size. The scheduled nightly run uses 12 seeds and 90 simulated seconds per team size. The workflow is pull-request triggered (not also push triggered) to avoid duplicate runs for the same PR update.

## How to use it from the Arena AI sandbox

1. Make changes on the PR branch and add regression tests.
2. Commit and push the changes.
3. Wait for both **Arena FC tests** and **Arena FC quality gates** on the exact new head SHA.
4. Inspect failed job logs and annotations; do not rely only on the green/red sum.
5. Download and inspect the stress logs, coverage reports and rendered captures from the workflow artifacts.

## What a passing run does and does not prove

- A passing asset job proves the committed manifest and GLB satisfy the checked structural contracts; it does not prove animation quality.
- A passing stress job proves the tested seeds/team sizes remained finite and matched their paired deterministic run; it is not exhaustive simulation verification.
- Coverage artifacts are an initial baseline, not a percentage gate. Inspect the reports before setting thresholds.
- Render captures prove scripts execute and emit PNGs. They do **not** prove golden-image equivalence, perceptual animation quality, correct world-space foot planting or absence of foot sliding. Those require the next visual-validation stage: deterministic camera/pose scenarios, golden or metric-based comparisons, and explicit world-space foot-contact/slide measurements.
- Branch protection remains a repository administrator configuration step.
