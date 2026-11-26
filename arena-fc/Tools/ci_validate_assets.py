#!/usr/bin/env python3
"""Strict, dependency-free validation for Arena FC's committed v1 clip manifest and GLB."""
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
    if manifest.get("version") != 1:
        fail(f"expected committed clip manifest version 1, got {manifest.get('version')!r}")
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
        f"manifest v1, {len(clips)} unique clips/pose keys, "
        f"{plant_clips} clips with foot plants, {contact_clips} contact clips, "
        f"{moving_clips} clips with non-zero root velocity, "
        f"GLB v{version} ({len(raw):,} bytes)"
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
