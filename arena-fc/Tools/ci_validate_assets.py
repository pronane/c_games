#!/usr/bin/env python3
"""Strict, dependency-free validation for Arena FC v1/v2 clip manifests and GLB."""
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


def normalized_curve(value: object, label: str, expected_samples: int) -> None:
    if not isinstance(value, list) or len(value) != expected_samples:
        fail(f"{label}: expected exactly {expected_samples} samples")
    for index, sample in enumerate(value):
        number = finite_number(sample, f"{label}[{index}]")
        if not 0.0 <= number <= 1.0:
            fail(f"{label}[{index}] must be normalized to [0,1]")


def validate(root: Path) -> None:
    manifest_path = root / "Data/clips/clip_manifest.json"
    glb_path = root / "Data/models/soccer_player.glb"
    if not manifest_path.is_file():
        fail(f"missing clip manifest: {manifest_path}")
    if not glb_path.is_file():
        fail(f"missing source GLB: {glb_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    version = manifest.get("version")
    if version not in (1, 2):
        fail(f"unsupported clip manifest version {version!r}; expected 1 or 2")
    if not isinstance(manifest.get("skeleton"), str) or not manifest["skeleton"]:
        fail("manifest.skeleton must be a non-empty string")
    if not isinstance(manifest.get("poseSource"), str) or not manifest["poseSource"]:
        fail("manifest.poseSource must be a non-empty string")

    clips = manifest.get("clips")
    if not isinstance(clips, list) or not clips:
        fail("manifest.clips must be a non-empty array")

    ids: set[str] = set()
    pose_keys: set[str] = set()
    contact_clips = 0
    plant_clips = 0
    moving_clips = 0
    for index, clip in enumerate(clips):
        label = f"clips[{index}]"
        if not isinstance(clip, dict):
            fail(f"{label}: expected object")

        for key, seen in (("id", ids), ("poseDataKey", pose_keys)):
            value = clip.get(key)
            if not isinstance(value, str) or not value.strip():
                fail(f"{label}.{key}: expected non-empty string")
            if value in seen:
                fail(f"{label}.{key}: duplicate value {value!r}")
            seen.add(value)

        category = clip.get("category")
        if not isinstance(category, str) or not category:
            fail(f"{label}.category: expected non-empty string")
        duration = finite_number(clip.get("duration"), f"{label}.duration")
        if duration <= 0:
            fail(f"{label}.duration must be positive")

        contact = finite_number(clip.get("contactFraction"), f"{label}.contactFraction")
        if contact != -1 and not 0 <= contact <= 1:
            fail(f"{label}.contactFraction must be -1 (no contact) or normalized [0,1]")

        frames = clip.get("footPlantFrames")
        sides = clip.get("footPlantSides")
        if not isinstance(frames, list) or not isinstance(sides, list) or len(frames) != len(sides):
            fail(f"{label}: footPlantFrames and footPlantSides must be equal-length arrays")
        for j, frame in enumerate(frames):
            phase = finite_number(frame, f"{label}.footPlantFrames[{j}]")
            if not 0 <= phase <= 1:
                fail(f"{label}.footPlantFrames[{j}] outside normalized clip phase")
            if sides[j] not in ("Left", "Right"):
                fail(f"{label}.footPlantSides[{j}] must be Left or Right")
        if frames:
            plant_clips += 1

        for key in ("rootVelocityX", "rootVelocityZ", "preferredSpeed", "preferredTurnRate"):
            finite_number(clip.get(key), f"{label}.{key}")
        if abs(float(clip["rootVelocityX"])) > 1e-6 or abs(float(clip["rootVelocityZ"])) > 1e-6:
            moving_clips += 1

        if not isinstance(clip.get("ballState"), str):
            fail(f"{label}.ballState must be a string")
        tags = clip.get("tags")
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            fail(f"{label}.tags must be an array of strings")
        bone_count = clip.get("boneCount")
        if isinstance(bone_count, bool) or not isinstance(bone_count, int) or bone_count <= 0:
            fail(f"{label}.boneCount must be a positive integer")
        if not isinstance(clip.get("loop"), bool):
            fail(f"{label}.loop must be boolean")
        if contact >= 0:
            contact_clips += 1

        if version == 2:
            start = finite_number(clip.get("contactWindowStart"), f"{label}.contactWindowStart")
            end = finite_number(clip.get("contactWindowEnd"), f"{label}.contactWindowEnd")
            if (start, end) != (-1, -1):
                if not (0 <= start <= end <= 1):
                    fail(f"{label}: contact window must be (-1,-1) or normalized with start <= end")
            normalized_curve(clip.get("plantCurveLeft"), f"{label}.plantCurveLeft", 32)
            normalized_curve(clip.get("plantCurveRight"), f"{label}.plantCurveRight", 32)

            samples = clip.get("rootVelocitySamples")
            if not isinstance(samples, list) or len(samples) != 64:
                fail(f"{label}.rootVelocitySamples: expected 64 finite X/Z samples")
            for j, sample in enumerate(samples):
                finite_number(sample, f"{label}.rootVelocitySamples[{j}]")

            source = clip.get("source")
            provenance = clip.get("provenance")
            if not isinstance(source, str) or not source:
                fail(f"{label}.source must be a non-empty string")
            if not isinstance(provenance, dict) or not isinstance(provenance.get("type"), str):
                fail(f"{label}.provenance must be an object with a string type")
            if provenance["type"] != source:
                fail(f"{label}.source and provenance.type must agree")

    if version == 2:
        plumbing = manifest.get("hypermotionDataPlumbing")
        if not isinstance(plumbing, dict):
            fail("manifest.hypermotionDataPlumbing must be an object in v2")
        if plumbing.get("phase") != 1 or plumbing.get("samples") != 32:
            fail("manifest.hypermotionDataPlumbing must declare phase=1 and samples=32")
        if not isinstance(plumbing.get("source"), str) or not plumbing["source"]:
            fail("manifest.hypermotionDataPlumbing.source must be a non-empty string")

    raw = glb_path.read_bytes()
    if len(raw) < 12:
        fail("source GLB is shorter than its 12-byte header")
    magic, glb_version, declared_length = struct.unpack("<4sII", raw[:12])
    if magic != b"glTF" or glb_version != 2:
        fail(f"invalid GLB header: magic={magic!r}, version={glb_version}")
    if declared_length != len(raw):
        fail(f"GLB declared length {declared_length} does not match file length {len(raw)}")

    print(
        "PASS asset contracts: "
        f"manifest v{version}, {len(clips)} unique clips/pose keys, "
        f"{plant_clips} clips with foot plants, {contact_clips} contact clips, "
        f"{moving_clips} clips with non-zero root velocity, "
        f"GLB v{glb_version} ({len(raw):,} bytes)"
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
