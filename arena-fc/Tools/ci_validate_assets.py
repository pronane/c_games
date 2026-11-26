#!/usr/bin/env python3
"""Strict, dependency-free CI validation for Arena FC's baked clip manifest and GLB."""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from pathlib import Path


def fail(message: str) -> None:
    raise ValueError(message)


def finite_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        fail(f"{label}: expected a number, got {type(value).__name__}")
    number = float(value)
    if not math.isfinite(number):
        fail(f"{label}: value must be finite")
    return number


def validate(root: Path) -> None:
    manifest_path = root / "Data/clips/clip_manifest.json"
    glb_path = root / "Data/models/soccer_player.glb"
    if not manifest_path.is_file():
        fail(f"missing clip manifest: {manifest_path}")
    if not glb_path.is_file():
        fail(f"missing source GLB: {glb_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("version") != 2:
        fail(f"manifest version must be 2, got {manifest.get('version')!r}")

    plumbing = manifest.get("hypermotionDataPlumbing")
    if not isinstance(plumbing, dict):
        fail("manifest is missing hypermotionDataPlumbing metadata")
    samples = int(plumbing.get("samples", 0))
    if samples < 2:
        fail(f"invalid manifest sample count: {samples}")

    clips = manifest.get("clips")
    if not isinstance(clips, list) or not clips:
        fail("manifest clips must be a non-empty array")

    ids: set[str] = set()
    root_velocity_nonzero = 0
    contact_windows = 0
    for index, clip in enumerate(clips):
        label = f"clips[{index}]"
        if not isinstance(clip, dict):
            fail(f"{label}: expected object")
        clip_id = clip.get("id")
        if not isinstance(clip_id, str) or not clip_id.strip():
            fail(f"{label}: missing non-empty id")
        if clip_id in ids:
            fail(f"{label}: duplicate clip id {clip_id!r}")
        ids.add(clip_id)

        duration = finite_number(clip.get("duration"), f"{label}.duration")
        if duration <= 0:
            fail(f"{label}.duration must be positive")

        for curve_name in ("plantCurveLeft", "plantCurveRight"):
            curve = clip.get(curve_name)
            if not isinstance(curve, list) or len(curve) != samples + 1:
                fail(f"{label}.{curve_name}: expected {samples + 1} samples")
            for j, value in enumerate(curve):
                weight = finite_number(value, f"{label}.{curve_name}[{j}]")
                if weight < -1e-5 or weight > 1.00001:
                    fail(f"{label}.{curve_name}[{j}] outside [0,1]: {weight}")

        root_samples = clip.get("rootVelocitySamples")
        if not isinstance(root_samples, list) or len(root_samples) != samples * 2:
            fail(f"{label}.rootVelocitySamples: expected {samples * 2} XZ values")
        for j, value in enumerate(root_samples):
            finite_number(value, f"{label}.rootVelocitySamples[{j}]")
        if any(abs(float(v)) > 1e-6 for v in root_samples):
            root_velocity_nonzero += 1

        start = finite_number(clip.get("contactWindowStart", -1), f"{label}.contactWindowStart")
        end = finite_number(clip.get("contactWindowEnd", -1), f"{label}.contactWindowEnd")
        if (start < 0) != (end < 0):
            fail(f"{label}: contact window must have both endpoints set or both unset")
        if start >= 0:
            if start > 1 or end > 1 or end < start:
                fail(f"{label}: invalid normalized contact window {start}..{end}")
            contact_windows += 1

        frames = clip.get("footPlantFrames", [])
        sides = clip.get("footPlantSides", [])
        if not isinstance(frames, list) or not isinstance(sides, list) or len(frames) != len(sides):
            fail(f"{label}: footPlantFrames and footPlantSides must be equal-length arrays")
        for j, frame in enumerate(frames):
            phase = finite_number(frame, f"{label}.footPlantFrames[{j}]")
            if phase < 0 or phase > 1:
                fail(f"{label}.footPlantFrames[{j}] outside normalized clip phase")
            if sides[j] not in ("Left", "Right"):
                fail(f"{label}.footPlantSides[{j}] must be Left or Right")

        provenance = clip.get("provenance")
        if not isinstance(provenance, dict) or not isinstance(provenance.get("type"), str):
            fail(f"{label}: missing per-clip provenance.type")

    raw = glb_path.read_bytes()
    if len(raw) < 12:
        fail("source GLB is shorter than its 12-byte header")
    magic, version, declared_length = struct.unpack("<4sII", raw[:12])
    if magic != b"glTF" or version != 2:
        fail(f"invalid GLB header: magic={magic!r}, version={version}")
    if declared_length != len(raw):
        fail(f"GLB declared length {declared_length} does not match file length {len(raw)}")

    print(
        "PASS asset contracts: "
        f"{len(clips)} unique clips, {samples} curve intervals, "
        f"{root_velocity_nonzero} clips with non-zero root velocity samples, "
        f"{contact_windows} contact windows, GLB v{version} ({len(raw):,} bytes)"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        validate(args.root.resolve())
        return 0
    except Exception as exc:
        print(f"FAIL asset contracts: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
