# Arena FC CI testing guide

## Why this exists

The Arena AI editing sandbox may not have Godot or .NET installed. GitHub Actions is the independent execution environment: it installs .NET 9 and Godot 4.7.2 Mono, builds the project, runs existing suites, exercises deterministic simulations, collects .NET coverage and renders screenshot artifacts.

A local agent must never describe a build, runtime test or rendered capture as successful unless the matching workflow ran on the commit being reported.

## Workflows

### Existing: Arena FC tests

`.github/workflows/arena-fc-tests.yml` remains the primary build/regression workflow. It covers the Godot C# build, server build, pure-C# suites, Godot headless self-test, GDScript checks and Node/network smoke tests.

### Added: Arena FC quality gates

`.github/workflows/arena-fc-quality.yml` adds:

- **Asset and Python contracts:** Python syntax compilation, validation against the repository's actual v1 clip manifest schema, normalized foot-plant/contact fields, unique clip and pose keys, finite motion metadata, and GLB header/length checks.
- **Seeded simulation stress:** paired identical-seed 5v5, 7v7 and 11v11 matches; compares authoritative state each tick and rejects non-finite player/ball state.
- **.NET coverage reports:** collects Cobertura reports from the existing CoreTests and MatchCoreTests console test runners using Microsoft's cross-platform `dotnet-coverage`.
- **Rendered evidence:** uses Xvfb and Mesa software rendering to execute the existing procedural-rig and browser-game screenshot scripts. PNGs are uploaded as workflow artifacts.

Pull-request stress runs use 3 seeds and 30 simulated seconds per team size. The scheduled nightly run uses 12 seeds and 90 simulated seconds per team size. The workflow is pull-request triggered (not also push triggered) to avoid duplicate runs for the same PR update.

## How to use it from the Arena AI sandbox

1. Make changes on the PR branch and add regression tests.
2. Commit and push the changes.
3. Wait for both **Arena FC tests** and **Arena FC quality gates** on the exact new head SHA.
4. Inspect failed job logs and annotations; do not rely only on the green/red summary.
5. Download the stress log, Cobertura files and rendered-capture artifact when relevant.
6. Fix the underlying defect, push again and repeat.

The sandbox can author code and inspect source, but it must not claim to have run Godot or .NET locally unless those executables really exist there.

## Coverage interpretation

The Cobertura reports are a baseline, not a quality score. These console suites are not yet converted to a standard test-framework project, so this workflow collects coverage around their existing executable runners. Review which assemblies and source files are represented before setting hard percentage gates. Do not set arbitrary global thresholds until the baseline has been inspected and the important domain code has adequate tests.

## Visual-test limitations

The rendered-capture job proves that the existing rig and browser gameplay capture scripts execute and produce PNGs under a software-rendered display. It does not yet compare the images against approved golden images, measure world-space foot sliding, validate the C# SoccerClipRig on every skeleton, or replace human review of animation quality. Those require dedicated deterministic Godot scenes and metrics before visual regression can be a strict merge gate.

## Branch protection

Repository administrators should configure a ruleset for `main` that requires the existing Arena FC test workflow and the new Arena FC quality-gates workflow. Select required check names from actual completed PR runs. Also require the branch to be up to date and block force pushes. The GitHub Actions files cannot safely grant or change repository branch-protection permissions themselves.
