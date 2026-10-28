# Motion fingerprint + stick-figure contact sheets for FBX2glTF clips (analysis helper).
import json,struct,sys,glob,os,numpy as np
from PIL import Image, ImageDraw
sys.path.insert(0,os.path.dirname(__file__))
def load(f):
    d=open(f,'rb').read(); l=struct.unpack('<I',d[12:16])[0]; j=json.loads(d[20:20+l]); o=20+l
    bl=struct.unpack('<I',d[o:o+4])[0]; return j,bytes(d[o+8:o+8+bl])
def acc(j,b,i):
    a=j['accessors'][i]; bv=j['bufferViews'][a['bufferView']]
    n={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}[a['type']]
    off=bv.get('byteOffset',0)+a.get('byteOffset',0)
    return np.frombuffer(b[off:off+4*n*a['count']],np.float32).reshape(a['count'],n)
def qmat(q):
    x,y,z,w=q/np.linalg.norm(q); return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
BONES=['pelvis','spine_02','neck_01','head','upperarm_l','lowerarm_l','hand_l','upperarm_r','lowerarm_r','hand_r','thigh_l','calf_l','foot_l','thigh_r','calf_r','foot_r']
LINKS=[(0,1),(1,2),(2,3),(2,4),(4,5),(5,6),(2,7),(7,8),(8,9),(0,10),(10,11),(11,12),(0,13),(13,14),(14,15)]
def sample(f,N=24):
    j,b=load(f); nodes=j['nodes']; names=[n.get('name','') for n in nodes]
    parent={}
    for i,n in enumerate(nodes):
        for c in n.get('children',[]): parent[c]=i
    an=j['animations'][0]; ch={}
    T=0
    for c in an['channels']:
        s=an['samplers'][c['sampler']]; tt=acc(j,b,s['input'])[:,0]; vv=acc(j,b,s['output']); T=max(T,tt[-1])
        ch[(c['target']['node'],c['target']['path'])]=(tt,vv)
    def val(i,p,t,default):
        if (i,p) not in ch: return np.array(default,float)
        tt,vv=ch[(i,p)]; k=np.searchsorted(tt,t)
        if k<=0: return vv[0].astype(float)
        if k>=len(tt): return vv[-1].astype(float)
        a=(t-tt[k-1])/(tt[k]-tt[k-1]+1e-9); return vv[k-1]*(1-a)+vv[k]*a
    def local(i,t):
        n=nodes[i]; m=np.eye(4)
        m[:3,:3]=qmat(val(i,'rotation',t,n.get('rotation',[0,0,0,1])))*val(i,'scale',t,n.get('scale',[1,1,1]))
        m[:3,3]=val(i,'translation',t,n.get('translation',[0,0,0])); return m
    ids=[names.index(x) for x in BONES]
    out=[]
    for t in np.linspace(0,T,N):
        cache={}
        def W(i):
            if i in cache: return cache[i]
            m=local(i,t) if i not in parent else W(parent[i])@local(i,t); cache[i]=m; return m
        out.append([W(i)[:3,3] for i in ids])
    P=np.array(out)  # N x B x 3
    # up axis = largest head-foot separation at t0
    d=P[0,3]-(P[0,12]+P[0,15])/2; up=np.argmax(np.abs(d)); sgn=np.sign(d[up])
    h=abs(d[up]); P=P/h
    return T,P,up,sgn
def feat(P,up):
    Q=P-P[:,:1,:]   # relative to pelvis
    return Q.reshape(len(Q),-1)
if __name__=='__main__':
    files=sys.argv[2:]; out=sys.argv[1]
    cells=[]
    for f in files:
        T,P,up,sgn=sample(f,8)
        cells.append((os.path.basename(f)[:-4],T,P,up,sgn))
    cw,chh=110,150; img=Image.new('RGB',(cw*8+150,chh*len(cells)),'white'); d=ImageDraw.Draw(img)
    for r,(nm,T,P,up,sgn) in enumerate(cells):
        d.text((4,r*chh+60),f'{nm}\n{T:.2f}s',fill='black')
        # side axis: choose horizontal axis with most pelvis/foot motion spread
        hor=[a for a in range(3) if a!=up]
        # project: x = forward axis (the horizontal with larger hand/foot spread)
        spread=[np.ptp(P[:,:,a]-P[:,:1,a]) for a in hor]; ax=hor[int(np.argmax(spread))]
        for k in range(8):
            ox=150+k*cw+cw/2; oy=r*chh+chh-10
            p=P[k]; base=P[k,0]
            for a,bb in LINKS:
                x1=ox+(p[a][ax]-base[ax])*60; y1=oy-(p[a][up]*sgn-min(P[0,:,up]*sgn))*60*1.0
                x2=ox+(p[bb][ax]-base[ax])*60; y2=oy-(p[bb][up]*sgn-min(P[0,:,up]*sgn))*60
                col='red' if bb in (13,14,15,7,8,9) else 'blue'
                d.line([x1,y1,x2,y2],fill=col,width=2)
    img.save(out)
