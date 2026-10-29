"""Accuracy of a scan of the bundled synthetic orbit clip against its ground-truth mesh.
  python tools/scan_eval.py --work out_scan/orbit_demo_scan [--json eval.json] MESH.obj [MESH2.obj ...]
(ground truth = examples_video/orbit_mannequin_truth.npz + orbit_mannequin_cameras.json, from the Blender render)"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
import argparse
import numpy as np, json
_ap = argparse.ArgumentParser(); _ap.add_argument("--work", required=True); _ap.add_argument("--json")
_ap.add_argument("--truth", default=os.path.join(ROOT, "examples_video", "orbit_mannequin_truth.npz"))
_ap.add_argument("--cameras", default=os.path.join(ROOT, "examples_video", "orbit_mannequin_cameras.json"))
_ap.add_argument("meshes", nargs="+"); A_ = _ap.parse_args()
from scipy.spatial import cKDTree
from sforge import scan
t=np.load(A_.truth); TV=t['V'][:,[0,2,1]]*np.array([1,1,-1]); TF=t['F']
def samp(V,F,n=30000,seed=0):
    r=np.random.default_rng(seed); A=np.linalg.norm(np.cross(V[F[:,1]]-V[F[:,0]],V[F[:,2]]-V[F[:,0]]),axis=1)
    f=r.choice(len(F),n,p=A/A.sum()); u=r.random((n,2)); m=u.sum(1)>1; u[m]=1-u[m]
    return V[F[f,0]]+u[:,:1]*(V[F[f,1]]-V[F[f,0]])+u[:,1:]*(V[F[f,2]]-V[F[f,0]])
def norm(P): lo,hi=P.min(0),P.max(0); return P-np.array([(lo[0]+hi[0])/2,lo[1],(lo[2]+hi[2])/2])
TP=norm(samp(TV,TF)); tree=cKDTree(TP)
def icp(P,yaw):
    a=np.radians(yaw); R=np.array([[np.cos(a),0,np.sin(a)],[0,1,0],[-np.sin(a),0,np.cos(a)]]); Q=P@R.T; s=1.0
    for it in range(30):
        d,i=tree.query(Q); m=d<np.percentile(d,90); A=Q[m]; B=TP[i[m]]
        ma,mb=A.mean(0),B.mean(0); H=(A-ma).T@(B-mb); U,S,Vt=np.linalg.svd(H); D=np.eye(3); D[2,2]=np.sign(np.linalg.det(Vt.T@U.T)); Rr=Vt.T@D@U.T
        sc=(S*np.diag(D)).sum()/((A-ma)**2).sum(); Q=(Q-ma)@Rr.T*sc+mb; s*=sc
    return Q,s
res={}
for nm in A_.meshes:
    V,F,C=scan.read_mesh(nm); P=norm(samp(V,F)); best=None
    for yaw in range(0,360,30):
        Q,s=icp(P,yaw); d=tree.query(Q)[0].mean()
        if best is None or d<best[0]: best=(d,Q,s)
    d,Q,s=best; d1=tree.query(Q)[0]; d2=cKDTree(Q).query(TP)[0]
    r={'tris':int(len(F)),'scan_to_truth_mean_cm':100*d1.mean(),'scan_to_truth_p90_cm':100*np.percentile(d1,90),
       'truth_to_scan_mean_cm':100*d2.mean(),'truth_to_scan_p90_cm':100*np.percentile(d2,90),'scale_fix':s,
       'within_2cm_pct':100*(d1<0.02).mean()}
    res[nm.split('/')[-1]]=r; print(nm.split('/')[-1], {k:round(float(v),2) for k,v in r.items()})
cams,imgs,pts=scan.read_colmap_txt(os.path.join(A_.work, 'sparse_txt'))
T=json.load(open(A_.cameras))['cameras']
A=np.array([-im['R'].T@im['t'] for im in imgs]); B=np.array([T[int(im['name'][6:10])]['location'] for im in imgs])
ma,mb=A.mean(0),B.mean(0); H=(A-ma).T@(B-mb); U,S,Vt=np.linalg.svd(H); D=np.eye(3); D[2,2]=np.sign(np.linalg.det(Vt.T@U.T)); R=Vt.T@D@U.T
s=(S*np.diag(D)).sum()/((A-ma)**2).sum(); E=np.linalg.norm((A-ma)@R.T*s+mb-B,axis=1)
res['cameras']={'mean_mm':1000*E.mean(),'max_mm':1000*E.max()}
print('camera centre error: mean %.1f mm max %.1f mm (orbit radius 3.2 m)'%(1000*E.mean(),1000*E.max()))
json.dump(res,open(A_.json or os.path.join(A_.work, 'scan_eval.json'),'w'),indent=1,default=float)
