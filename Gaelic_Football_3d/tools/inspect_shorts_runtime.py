#!/usr/bin/env python3
"""Compare skinned shorts hems before and after the actual jog leg IK.

Runs the raylib 5.5 headless frontend in a straight jog or a synthetic turn,
run and stop sequence, and samples paired model-space poses after a one-second
warmup. GLB vertices are linearly skinned with each pose. No renderer, live
match, ball actions or occlusion is simulated.
"""
import argparse
import json
import math
import subprocess
import tempfile
from pathlib import Path

from inspect_shorts_skin import load_glb
from inspect_shorts_motion import measure


def compare(model, tool, speed, fps, no_ik=False, scenario='straight'):
    if scenario not in ('straight', 'turn-transition'): raise ValueError('unknown scenario')
    with tempfile.TemporaryDirectory(prefix='shorts-runtime-') as directory:
        output = Path(directory) / 'poses.json'
        command = [str(Path(tool).resolve()), '--export-jog-poses' if scenario == 'straight' else '--export-turn-poses',
                   str(Path(model).resolve()), str(output)]
        if scenario == 'straight': command.append(str(speed))
        command.append(str(fps))
        if no_ik: command.append('--no-ik')
        subprocess.run(command, check=True)
        data = json.loads(output.read_text())
    if data.get('format') != 1 or data['fps'] != fps or not data['frames']:
        raise ValueError('invalid pose export metadata')
    doc, blob = load_glb(model)
    joint_names = [doc['nodes'][i].get('name', '') for i in doc['skins'][0]['joints']]
    names = data['bones']
    if len(set(names)) != len(names) or len(set(joint_names)) != len(joint_names):
        raise ValueError('ambiguous joint names')
    lookup = {name: i for i, name in enumerate(names)}
    if set(joint_names) != set(names): raise ValueError('model and pose skeletons differ')
    joint_order = [lookup[name] for name in joint_names]
    source, adjusted = [], []
    for frame in data['frames']:
        for key, target in (('raw', source), ('adjusted', adjusted)):
            if len(frame[key]) != len(names): raise ValueError('incomplete joint pose')
            target.append([frame[key][i] for i in joint_order])
    a = measure(doc, blob, frames=len(source), world_frames=source, include_values=True)
    b = measure(doc, blob, frames=len(adjusted), world_frames=adjusted, include_values=True)
    raw_values = a.pop('_vertex_values'); ik_values = b.pop('_vertex_values')
    comparisons = []; temporal = []
    for mesh in a['shorts']:
        name = mesh['mesh']; sides = {}
        for i, side in enumerate(('positive_x', 'negative_x')):
            raw = raw_values[name][i]; post = ik_values[name][i]
            if len(raw) != len(post): raise ValueError('unaligned samples')
            diffs, means = [], []
            for r, p in zip(raw, post):
                if not r or len(r) != len(p): raise ValueError('unaligned hem vertices')
                delta = [y-x for x,y in zip(r,p)]
                diffs.extend(delta); means.append(sum(delta)/len(delta))
            sides[side] = {
                'max_abs_mean_hem_delta_m': max(map(abs, means)),
                'max_abs_vertex_delta_m': max(map(abs, diffs)),
                'rms_vertex_delta_m': math.sqrt(sum(x*x for x in diffs)/len(diffs)),
            }
        comparisons.append({'mesh': name, 'sides': sides})
        if scenario == 'turn-transition':
            groups = {}
            for i, side in enumerate(('positive_x', 'negative_x')):
                values = ik_values[name][i]; by_phase = {}
                for step in range(1, len(values)):
                    frame = data['frames'][step]
                    if frame['turn_rate'] > 2.0: phase = 'turn'
                    elif frame['blend'] < .999: phase = 'crossfade'
                    else: phase = 'steady'
                    delta = [x-y for x,y in zip(values[step], values[step-1])]
                    stat = by_phase.setdefault(phase, {'samples':0, 'max_abs_mean_step_m':0.0, 'max_abs_vertex_step_m':0.0})
                    stat['samples'] += 1
                    stat['max_abs_mean_step_m'] = max(stat['max_abs_mean_step_m'], abs(sum(delta)/len(delta)))
                    stat['max_abs_vertex_step_m'] = max(stat['max_abs_vertex_step_m'], max(map(abs, delta)))
                groups[side] = by_phase
            temporal.append({'mesh': name, 'sides': groups})
    summary = {}
    if scenario == 'turn-transition':
        from collections import Counter
        summary = {'clip_frame_counts': dict(Counter(f['clip'] for f in data['frames'])),
                   'crossfade_frames': sum(f['blend'] < .999 for f in data['frames']),
                   'turn_frames': sum(f['turn_rate'] > 2 for f in data['frames'])}
    return {
        'model': str(model), 'fps': fps, 'scenario': scenario, 'speed_mps': speed if scenario == 'straight' else None,
        'scenario_summary': summary,
        'samples': len(source), 'warmup_seconds': data['warmup_seconds'], 'ik_applied': data['ik'],
        'limitation': 'synthetic headless raylib 5.5 poses and GLB linear skinning; no rendered mesh, live gameplay, ball actions, raylib 6 or occlusion',
        'raw': a['shorts'], 'adjusted': b['shorts'], 'paired_ik_delta': comparisons, 'frame_steps': temporal,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model'); parser.add_argument('--tool', required=True, help='built motion_headless executable')
    parser.add_argument('--speed', type=float, default=2.0); parser.add_argument('--fps', type=int, choices=(30,60), default=60)
    parser.add_argument('--scenario', choices=('straight', 'turn-transition'), default='straight')
    args = parser.parse_args()
    print(json.dumps(compare(args.model, args.tool, args.speed, args.fps, scenario=args.scenario), indent=2))


if __name__ == '__main__': main()
