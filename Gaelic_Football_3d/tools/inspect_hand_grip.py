#!/usr/bin/env python3
"""Screen selected CPU-skinned finger surfaces after scripted ball cradling.

Derives bind rotations from GLB node transforms, verifies inverse binds, and
runs the frontend's raylib 5.5 headless cradle on hand-picked clip phases.
This is not live gameplay, a complete mesh test, or rendered ball validation.
"""
import argparse
import json
import math
import subprocess
import tempfile
from pathlib import Path
from inspect_shorts_skin import load_glb, accessor
from inspect_shorts_motion import mul, trs
from inspect_hand_mesh import measure


def qmul(a,b):
    x,y,z,w=a; X,Y,Z,W=b
    return (w*X+x*W+y*Z-z*Y,w*Y-x*Z+y*W+z*X,w*Z+x*Y-y*X+z*W,w*W-x*X-y*Y-z*Z)


def bind_rotations(doc,blob):
    nodes=doc['nodes']; joints=doc['skins'][0]['joints']; parents={}
    for i,n in enumerate(nodes):
        if 'matrix' in n: raise ValueError('matrix nodes unsupported')
        scale=n.get('scale',(1,1,1))
        if any(not math.isfinite(x) or x<=0 for x in scale) or max(scale)-min(scale)>1e-5:
            raise ValueError('nonuniform or invalid bind scale')
        for child in n.get('children',[]):
            if child in parents: raise ValueError('multiple parents')
            parents[child]=i
    cache={}; active=set()
    def world(i):
        if i in cache: return cache[i]
        if i in active: raise ValueError('cyclic hierarchy')
        active.add(i); n=nodes[i]; q=n.get('rotation',(0,0,0,1)); size=math.sqrt(sum(x*x for x in q))
        if not math.isfinite(size) or size<1e-9: raise ValueError('invalid quaternion')
        q=tuple(x/size for x in q)
        m=trs(n.get('translation',(0,0,0)),q,n.get('scale',(1,1,1)))
        if i in parents:
            pm,pq=world(parents[i]); m=mul(pm,m); q=qmul(pq,q)
        active.remove(i); cache[i]=(m,q); return cache[i]
    ibm=accessor(doc,blob,doc['skins'][0]['inverseBindMatrices'])
    if len(ibm)!=len(joints): raise ValueError('invalid inverse binds')
    lines=[]; names=set()
    for idx,j in enumerate(joints):
        name=nodes[j].get('name',''); m,q=world(j)
        if not name or any(c.isspace() for c in name) or name in names: raise ValueError('invalid bone name')
        names.add(name); inv=[[ibm[idx][c*4+r] for c in range(4)] for r in range(4)]; product=mul(m,inv)
        if any(abs(product[r][c]-(1 if r==c else 0))>.001 for r in range(4) for c in range(4)):
            raise ValueError('GLB bind mismatch')
        lines.append(name+' '+' '.join(f'{x:.9g}' for x in q))
    return '\n'.join(lines)+'\n'


def compare_renderer_bind(expected, actual):
    a=expected.strip().splitlines(); b=actual.strip().splitlines()
    if len(a)!=len(b) or not a: raise ValueError('renderer bone count differs')
    maximum=0.0
    for x,y in zip(a,b):
        x=x.split(); y=y.split()
        if len(x)!=5 or len(y)!=5 or x[0]!=y[0]: raise ValueError('renderer bone order differs')
        q=[float(v) for v in x[1:]]; r=[float(v) for v in y[1:]]
        n=math.sqrt(sum(v*v for v in q)); m=math.sqrt(sum(v*v for v in r))
        if not math.isfinite(n) or not math.isfinite(m) or min(n,m)<.99: raise ValueError('invalid bind quaternion')
        angle=2*math.acos(min(1.,abs(sum(a*b for a,b in zip(q,r))/(n*m))))
        maximum=max(maximum,angle)
    if maximum>.001: raise ValueError(f'renderer bind rotation differs by {maximum:.6f} rad')
    return maximum


def compare(model,tool,clearance=None,sprint_offset=None):
    doc,blob=load_glb(model)
    with tempfile.TemporaryDirectory(prefix='hand-grip-') as tmp:
        tmp=Path(tmp); bind=tmp/'bind.txt'; out=tmp/'poses.json'
        bind.write_text(bind_rotations(doc,blob))
        command=[str(Path(tool).resolve()),'--export-grip-poses',str(Path(model).resolve()),str(out),str(bind)]
        if sprint_offset is not None and clearance is None: raise ValueError('sprint offset requires explicit clearance')
        if clearance is not None: command.append(str(clearance))
        if sprint_offset is not None: command.extend(str(x) for x in sprint_offset)
        proc=subprocess.run(command,capture_output=True,text=True,check=True)
        data=json.loads(out.read_text())
    if data.get('scenario')!='scripted-grip' or len(data['frames'])!=12: raise ValueError('invalid grip export')
    for f in data['frames']:
        if f['raw']!=f['adjusted']: raise ValueError('guarded correction changed grip')
    report=measure(doc,blob,data,surface=True)
    return {'limitation':'12 synthetic sampled CPU poses, selected finger surfaces, approximate ball sphere; no gameplay, full mesh, rendered or continuous collision validation',
            'samples':report['surface_samples'], 'clearance_m':data['clearance_m'], 'sprint_offset_m':sprint_offset or [0,0,0], 'pose_export':proc.stdout.strip(),
            'triangle_counts':report['selected_surface_triangles'], 'palm_surface_triangles':report['palm_surface_triangles'], 'hand_surface_triangles':report['hand_surface_triangles'], 'states':report['sampled_surface_by_state'],
            'ball_available':[f['state'] for f in data['frames'] if f['ball_center'] is not None],
            'cradle_weights':{f['state']:f['cradle_weight'] for f in data['frames']}}


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('model'); p.add_argument('--tool'); p.add_argument('--check-renderer-bind'); p.add_argument('--clearance',type=float); p.add_argument('--sprint-offset',type=float,nargs=3,metavar=('X','Y','Z'))
    a=p.parse_args()
    if a.check_renderer_bind:
        d,b=load_glb(a.model); print('renderer_bind_max_rad',compare_renderer_bind(bind_rotations(d,b),Path(a.check_renderer_bind).read_text()))
    elif a.tool: print(json.dumps(compare(a.model,a.tool,a.clearance,a.sprint_offset),indent=2))
    else: p.error('--tool or --check-renderer-bind required')
if __name__=='__main__': main()
