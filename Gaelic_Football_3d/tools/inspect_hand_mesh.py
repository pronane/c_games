#!/usr/bin/env python3
"""Compare skinned fingertip proxy vertices in paired headless jog poses.

Fingertips are approximated using distal-bone weights and bind-space extension.
Adjacent gaps are sampled-vertex distances, not surface or collision tests.
This is CPU glTF linear skinning, not the rendered mesh or gameplay.
"""
import argparse
import json
import math
import subprocess
import tempfile
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "shared/arena_motion"))
from mesh_diagnostics import centroid, distance, sampled_min_distance, skin_point, triangles_intersect, triangle_overlap_pairs, point_triangle_distance
from inspect_shorts_skin import load_glb, accessor
from inspect_shorts_motion import mul, trs

FINGERS = ('index', 'middle', 'ring', 'pinky')


def select_tips(points, ids, weights, bone, origin, axis):
    size = math.sqrt(sum(x*x for x in axis))
    if size < 1e-8: raise ValueError('degenerate finger axis')
    axis = [x/size for x in axis]
    candidates = []
    for i, (point, js, ws) in enumerate(zip(points, ids, weights)):
        if sum(w for j,w in zip(js,ws) if j == bone) >= .5:
            candidates.append((sum((point[k]-origin[k])*axis[k] for k in range(3)), i))
    if len(candidates) < 5: raise ValueError('insufficient distal-weighted vertices')
    candidates.sort(reverse=True)
    # A small distal cap, not a guessed anatomical fingertip vertex.
    return [i for _,i in candidates[:max(3, math.ceil(len(candidates)*.2))]]


def measure(doc, blob, data, surface=False):
    if data.get('format') != 1 or not data.get('frames'): raise ValueError('invalid pose export')
    nodes=doc['nodes']; skin=doc['skins'][0]; joints=skin['joints']
    names=[nodes[i].get('name','') for i in joints]; exported=data['bones']
    if len(set(names)) != len(names) or len(set(exported)) != len(exported) or set(names) != set(exported):
        raise ValueError('pose and GLB joint names mismatch')
    order=[exported.index(name) for name in names]
    parent={}
    for i,node in enumerate(nodes):
        if 'matrix' in node: raise ValueError('matrix nodes unsupported')
        for child in node.get('children',[]):
            if child in parent: raise ValueError('multiple parents')
            parent[child]=i
    cache={}; active=set()
    def bind_world(i):
        if i in cache: return cache[i]
        if i in active: raise ValueError('cyclic hierarchy')
        active.add(i); n=nodes[i]; local=trs(n.get('translation',(0,0,0)),n.get('rotation',(0,0,0,1)),n.get('scale',(1,1,1)))
        cache[i]=mul(bind_world(parent[i]),local) if i in parent else local
        active.remove(i); return cache[i]
    raw=accessor(doc,blob,skin['inverseBindMatrices'])
    if len(raw) != len(joints): raise ValueError('bad inverse bind count')
    ibm=[[[a[c*4+r] for c in range(4)] for r in range(4)] for a in raw]
    for i,j in enumerate(joints):
        m=mul(bind_world(j),ibm[i])
        if any(abs(m[r][c]-(1 if r==c else 0)) > .001 for r in range(4) for c in range(4)):
            raise ValueError('raylib and GLB bind conventions differ')
    meshes=[n for n in nodes if n.get('skin')==0 and 'mesh' in n and doc['meshes'][n['mesh']].get('name')=='v0_body']
    if len(meshes)!=1: raise ValueError('expected one v0_body mesh')
    prims=doc['meshes'][meshes[0]['mesh']]['primitives']
    if len(prims)!=1: raise ValueError('expected one body primitive')
    attrs=prims[0]['attributes']; points=accessor(doc,blob,attrs['POSITION']); ids=accessor(doc,blob,attrs['JOINTS_0']); weights=accessor(doc,blob,attrs['WEIGHTS_0'])
    if not points or len(points)!=len(ids) or len(points)!=len(weights): raise ValueError('inconsistent body geometry')
    tips={}
    for side in ('l','r'):
        for finger in FINGERS:
            j2=names.index(f'{finger}_02_{side}'); j3=names.index(f'{finger}_03_{side}')
            a=[bind_world(joints[j2])[k][3] for k in range(3)]; b=[bind_world(joints[j3])[k][3] for k in range(3)]
            tips[(side,finger)]=select_tips(points,ids,weights,j3,b,[b[k]-a[k] for k in range(3)])
    surfaces = {}; surface_samples = 0; surface_by_state = []
    surface_stats = {side:{kind:{'overlap_pairs':0,'frames_with_overlap':0} for kind in ('raw','adjusted')} for side in ('l','r')}
    if surface:
        primitive=prims[0]
        if primitive.get('mode',4)!=4: raise ValueError('expected triangle list')
        indices=[int(v[0]) for v in accessor(doc,blob,primitive['indices'])]
        if len(indices)%3 or any(i<0 or i>=len(points) for i in indices): raise ValueError('invalid triangle indices')
        for side in ('l','r'):
            for finger in (*FINGERS,'thumb'):
                all_bones={names.index(f'{finger}_{j:02}_{side}') for j in (1,2,3)}
                distal={names.index(f'{finger}_{j:02}_{side}') for j in (2,3)}
                eligible=[sum(w for j,w in zip(js,ws) if j in all_bones)>=.75 and
                          sum(w for j,w in zip(js,ws) if j in distal)>=.25 for js,ws in zip(ids,weights)]
                surfaces[(side,finger)]=[tuple(indices[i:i+3]) for i in range(0,len(indices),3)
                                         if all(eligible[j] for j in indices[i:i+3])]
                if not surfaces[(side,finger)]: raise ValueError('finger surface selection empty')
    result={side:{'gap_raw':[], 'gap_adjusted':[], 'min_sampled_raw':[], 'min_sampled_adjusted':[], 'max_tip_displacement':0.0} for side in ('l','r')}
    for frame_index,frame in enumerate(data['frames']):
        samples={}
        do_surface = surface and frame_index in {i*len(data['frames'])//12 for i in range(12)}
        if do_surface:
            surface_samples += 1
            state_stats={'state':frame.get('state',str(frame_index)), 'sides':{side:{} for side in ('l','r')}}
            if frame.get('ball_center') is not None: state_stats['ball_triangle_overlap']={side:{} for side in ('l','r')}
        for kind in ('raw','adjusted'):
            rows=frame[kind]
            if len(rows)!=len(order): raise ValueError('incomplete pose')
            matrices=[]
            for i in order:
                row=rows[i]
                if len(row)!=10 or any(not math.isfinite(x) for x in row): raise ValueError('invalid pose')
                matrices.append(trs(row[:3],row[3:7],row[7:]))
            mats=[mul(m,inv) for m,inv in zip(matrices,ibm)]
            samples[kind]={key:[skin_point(points[i],ids[i],weights[i],mats) for i in selected] for key,selected in tips.items()}
            if do_surface:
                chosen={i for tris in surfaces.values() for tri in tris for i in tri}
                verts={i:skin_point(points[i],ids[i],weights[i],mats) for i in chosen}
                for side in ('l','r'):
                    tris={finger:[[verts[i] for i in tri] for tri in surfaces[(side,finger)]] for finger in (*FINGERS,'thumb')}
                    overlap=sum(triangle_overlap_pairs(tris[a],tris[b]) for i,a in enumerate((*FINGERS,'thumb')) for b in (*FINGERS,'thumb')[i+1:])
                    surface_stats[side][kind]['overlap_pairs'] += overlap
                    surface_stats[side][kind]['frames_with_overlap'] += overlap>0
                    state_stats['sides'][side][kind]=overlap
                    if frame.get('ball_center') is not None:
                        center=frame['ball_center']; radius=frame['ball_radius']
                        if not isinstance(radius,(int,float)) or not math.isfinite(radius) or radius<=0: raise ValueError('invalid ball radius')
                        state_stats['ball_triangle_overlap'][side][kind]=sum(point_triangle_distance(center,t)<radius for group in tris.values() for t in group)
        if do_surface: surface_by_state.append(state_stats)
        for side in ('l','r'):
            for finger in FINGERS:
                key=(side,finger)
                result[side]['max_tip_displacement']=max(result[side]['max_tip_displacement'], *(distance(a,b) for a,b in zip(samples['raw'][key],samples['adjusted'][key])))
            for kind in ('raw','adjusted'):
                for a,b in zip(FINGERS,FINGERS[1:]):
                    aa=samples[kind][(side,a)]; bb=samples[kind][(side,b)]
                    ca=centroid(aa); cb=centroid(bb)
                    result[side]['gap_'+kind].append(distance(ca,cb))
                    result[side]['min_sampled_'+kind].append(sampled_min_distance(aa,bb))
    summary={}
    for side,d in result.items():
        summary[side]={'mean_adjacent_tip_centroid_gap_raw_m':sum(d['gap_raw'])/len(d['gap_raw']),
                       'mean_adjacent_tip_centroid_gap_adjusted_m':sum(d['gap_adjusted'])/len(d['gap_adjusted']),
                       'minimum_sampled_tip_vertex_gap_raw_m':min(d['min_sampled_raw']),
                       'minimum_sampled_tip_vertex_gap_adjusted_m':min(d['min_sampled_adjusted']),
                       'max_tip_vertex_displacement_m':d['max_tip_displacement']}
    return {'samples':len(data['frames']), 'mode':data['mode'],
            'tip_vertex_counts':{f'{s}_{f}':len(v) for (s,f),v in tips.items()}, 'sides':summary,
            'surface_samples':surface_samples, 'selected_surface_triangles':{f'{s}_{f}':len(v) for (s,f),v in surfaces.items()},
            'sampled_surface_overlap':surface_stats if surface else None,
            'sampled_surface_by_state':surface_by_state if surface else None,
            'limitation':'v0_body fingertip caps and selected distal finger triangles at sampled phases only; no palm, proximal surface, containment, continuous collision, render or anatomical validation'}


def compare(model, tool, mode=1, fps=30, surface=False):
    with tempfile.TemporaryDirectory(prefix='hand-mesh-') as tmp:
        out=Path(tmp)/'poses.json'
        subprocess.run([str(Path(tool).resolve()),'--export-hand-poses',str(Path(model).resolve()),str(out),str(mode),str(fps)],check=True,stdout=subprocess.DEVNULL)
        data=json.loads(out.read_text())
    doc,blob=load_glb(model)
    return measure(doc,blob,data,surface=surface)


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('model'); p.add_argument('--tool',required=True)
    p.add_argument('--mode',type=int,choices=(0,1,2,3,4),default=1); p.add_argument('--fps',type=int,choices=(30,60),default=30)
    p.add_argument('--surface',action='store_true',help='test selected distal finger triangles at 12 phases')
    a=p.parse_args(); print(json.dumps(compare(a.model,a.tool,a.mode,a.fps,a.surface),indent=2))

if __name__=='__main__': main()
