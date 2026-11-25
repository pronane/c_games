#!/usr/bin/env python3
"""Phase 1 Hypermotion data plumbing: enrich clip_manifest.json with v2 fields.

Adds plantCurveLeft/Right (uniformly sampled weights), contactWindowStart/End,
and rootVelocitySamples (uniform facing-local XZ samples). The bake is
deterministic and backward-compatible. When GLB/JSON pose data is available,
replace the heuristics with sampled curves from actual foot/root motion.
"""
from __future__ import annotations
import json, math, os, sys

SAMPLES = 32


def circ_diff(a, b):
    d = (a - b) % 1.0
    if d > 0.5:
        d -= 1.0
    if d < -0.5:
        d += 1.0
    return d


def plant_curve(frames, sides, side, samples=SAMPLES):
    curve = [0.0] * samples
    for f, s in zip(frames, sides):
        if str(s).lower() != side:
            continue
        for i in range(samples):
            p = i / (samples - 1)
            d = abs(circ_diff(p, float(f)))
            # Gaussian-ish plant weight around discrete event.
            w = math.exp(-(d * d) / (2 * 0.035 * 0.035))
            if w > curve[i]:
                curve[i] = w
    # normalize small numeric noise
    return [round(min(1.0, max(0.0, v)), 6) for v in curve]


def contact_window(contact_frac, duration):
    if contact_frac is None or float(contact_frac) < 0:
        return -1.0, -1.0
    cf = float(contact_frac)
    # Simple window: 20% of clip before contact to contact (clamped).
    start = max(0.0, cf - 0.20)
    end = min(1.0, cf + 0.05)
    return round(start, 6), round(end, 6)


def root_velocity_samples(vx, vz, samples=SAMPLES):
    # Phase 1: constant sample from avg velocity. Phase 2 can sample real curves.
    return [round(float(vx), 6), round(float(vz), 6)] * samples


def enrich_clip(c):
    frames = c.get('footPlantFrames', []) or []
    sides = c.get('footPlantSides', []) or []
    if len(sides) != len(frames):
        sides = ['Left' if i % 2 == 0 else 'Right' for i in range(len(frames))]
    c['footPlantSides'] = sides
    c['plantCurveLeft'] = plant_curve(frames, sides, 'left')
    c['plantCurveRight'] = plant_curve(frames, sides, 'right')
    ws, we = contact_window(c.get('contactFraction', -1.0), c.get('duration', 1.0))
    c['contactWindowStart'] = ws
    c['contactWindowEnd'] = we
    vx = c.get('rootVelocityX', 0.0) or 0.0
    vz = c.get('rootVelocityZ', 0.0) or 0.0
    c['rootVelocitySamples'] = root_velocity_samples(vx, vz)
    return c


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else 'arena-fc/Data/clips/clip_manifest.json'
    with open(path) as f:
        data = json.load(f)
    data['version'] = 2
    data['hypermotionDataPlumbing'] = {
        'phase': 1,
        'samples': SAMPLES,
        'note': 'Plant/contact/root-velocity curves baked deterministically from v1 metadata; replace with GLB-sampled curves when available.'
    }
    for c in data.get('clips', []):
        enrich_clip(c)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
    print(f"enriched {len(data.get('clips', []))} clips -> {path}")


if __name__ == '__main__':
    main()
