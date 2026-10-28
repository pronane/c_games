# Builds assets/models/gaelic_player.glb: skinned player + all anim_*.fbx animations,
# baked so raylib (which only animates skin joints) sees a correct, upright, metre-scale rig.
import json,struct,sys,io,numpy as np
from PIL import Image, ImageDraw
PROJ=sys.argv[1]; SRC=sys.argv[2] if len(sys.argv)>2 else 'build_gltf'
def load(f):
    d=open(f,'rb').read(); l=struct.unpack('<I',d[12:16])[0]; j=json.loads(d[20:20+l]); o=20+l
    bl=struct.unpack('<I',d[o:o+4])[0]; return j,bytearray(d[o+8:o+8+bl])
def acc(j,b,i):
    a=j['accessors'][i]; bv=j['bufferViews'][a['bufferView']]
    n={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}[a['type']]
    dt={5126:np.float32,5123:np.uint16,5121:np.uint8,5125:np.uint32}[a['componentType']]
    off=bv.get('byteOffset',0)+a.get('byteOffset',0); stride=bv.get('byteStride',0)
    isz=np.dtype(dt).itemsize*n
    if stride and stride!=isz:
        return np.stack([np.frombuffer(b,dt,n,off+k*stride) for k in range(a['count'])])
    return np.frombuffer(bytes(b[off:off+isz*a['count']]),dt).reshape(a['count'],n).copy()
def qmul(a,b):
    x1,y1,z1,w1=a; x2,y2,z2,w2=b
    return np.array([w1*x2+x1*w2+y1*z2-z1*y2, w1*y2-x1*z2+y1*w2+z1*x2, w1*z2+x1*y2-y1*x2+z1*w2, w1*w2-x1*x2-y1*y2-z1*z2])
def qrot(q,v):
    u=np.array(q[:3]); w=q[3]; v=np.array(v); return v+2*np.cross(u,np.cross(u,v)+w*v)
def qmat(q):
    x,y,z,w=q; return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
def trs(n):
    m=np.eye(4); m[:3,:3]=qmat(n.get('rotation',[0,0,0,1]))*np.array(n.get('scale',[1,1,1])); m[:3,3]=n.get('translation',[0,0,0]); return m

j,b=load(f'{SRC}/player_base.glb')
names=[n['name'] for n in j['nodes']]; idx={n:i for i,n in enumerate(names)}
GE,ROOT,PEL=idx['Game_engine'],idx['Root'],idx['pelvis']
R=j['nodes'][ROOT]; P=j['nodes'][PEL]
def bake(ge_t,ge_r,pel):  # world of pelvis = GE(t,r,scale 1) * Root * pelvis  -> TRS
    q=qmul(ge_r,qmul(R['rotation'],pel['rotation']))
    t=np.array(ge_t)+qrot(ge_r,qrot(R['rotation'],pel['translation'])+np.array(R['translation']))
    return t,q/np.linalg.norm(q)
t,q=bake([0,0,0],[0,0,0,1],P)
P['translation']=t.tolist(); P['rotation']=q.tolist(); P['scale']=[1,1,1]
j['nodes'][0]['children']=[PEL]+[c for c in j['nodes'][0]['children'] if c!=GE]
j['nodes'][ROOT]['children']=[]
for n in j['nodes']:
    if 'mesh' in n: n['scale']=[1,1,1]; n['skin']=0
# world matrices
parent={}
for i,n in enumerate(j['nodes']):
    for c in n.get('children',[]): parent[c]=i
def world(i): return trs(j['nodes'][i]) if i not in parent else world(parent[i])@trs(j['nodes'][i])
skin=j['skins'][0]; joints=skin['joints']
print('pelvis world', world(PEL)[:3,3], 'head', world(idx['head'])[:3,3])
# eyes mesh: remap its single joint (head) into skin 0
head_i=joints.index(idx['head'])
ja=j['accessors'][j['meshes'][1]['primitives'][0]['attributes']['JOINTS_0']]; bv=j['bufferViews'][ja['bufferView']]
o=bv.get('byteOffset',0)+ja.get('byteOffset',0)
arr=np.frombuffer(bytes(b[o:o+ja['count']*8]),np.uint16).reshape(-1,4).copy()
w=acc(j,b,j['meshes'][1]['primitives'][0]['attributes']['WEIGHTS_0'])
arr[:]=0; arr[:,0]=head_i; b[o:o+ja['count']*8]=arr.tobytes()
wa=j['accessors'][j['meshes'][1]['primitives'][0]['attributes']['WEIGHTS_0']]; wbv=j['bufferViews'][wa['bufferView']]
wo=wbv.get('byteOffset',0)+wa.get('byteOffset',0); w[:]=0; w[:,0]=1; b[wo:wo+w.nbytes]=w.astype(np.float32).tobytes()
j['skins']=[skin]
def add(data,ctype,typ,count,mn=None,mx=None):
    global b
    while len(b)%4: b.append(0)
    j['bufferViews'].append({'buffer':0,'byteOffset':len(b),'byteLength':len(data)}); b+=data
    a={'bufferView':len(j['bufferViews'])-1,'componentType':ctype,'type':typ,'count':count}
    if mn is not None: a['min']=mn; a['max']=mx
    j['accessors'].append(a); return len(j['accessors'])-1
ibm=np.stack([np.linalg.inv(world(x)).T.astype(np.float32) for x in joints])  # column-major
skin['inverseBindMatrices']=add(ibm.tobytes(),5126,'MAT4',len(joints))
skin.pop('skeleton',None)
# --- animations
j['animations']=[]
import os
ANIMS=[x.split(':') for x in os.environ.get('ANIMS',','.join('anim_%s:%s'%(n,n) for n in ['run','drop_kick','catch','idle','kick_run','hand_pass','kick_out','solo','dive_roll','keeper_ready','dive_high','get_up','run_ball','dive_save','pickup',
    # v3 clips (renamed from the second upload, see README)
    'kick_place','hook','head_hit','hit_react','knocked_down','trip','stumble','pushed','tackle_reach',
    'celebrate_jump','jog','sidestep','toe_lift','solo_left','keeper_high_catch','keeper_scoop','keeper_idle'])).split(',')]
for fn,nm in ANIMS:
    aj,ab=load(f'{SRC}/{fn}.glb'); an=aj['animations'][0]; anames=[n['name'] for n in aj['nodes']]
    ch=[]; sm=[]; ge={}
    for c in an['channels']:
        s=an['samplers'][c['sampler']]; nn=anames[c['target']['node']]
        tin=acc(aj,ab,s['input']); tout=acc(aj,ab,s['output'])
        if nn=='Game_engine': ge[c['target']['path']]=(tin[:,0],tout); continue
        if nn not in idx: continue
        ii=add(tin.astype(np.float32).tobytes(),5126,'SCALAR',len(tin),[float(tin.min())],[float(tin.max())])
        oo=add(tout.astype(np.float32).tobytes(),5126,c['target']['path']=='rotation' and 'VEC4' or 'VEC3',len(tout))
        sm.append({'input':ii,'output':oo,'interpolation':s.get('interpolation','LINEAR')})
        ch.append({'sampler':len(sm)-1,'target':{'node':idx[nn],'path':c['target']['path']}})
    times=np.unique(np.concatenate([v[0] for v in ge.values()]))
    def samp(path,dflt,t):
        if path not in ge: return np.array(dflt)
        ti,vo=ge[path]; return np.array([np.interp(t,ti,vo[:,k]) for k in range(vo.shape[1])])
    T=[];Q=[]; t0=samp('translation',[0,0,0],times[0])
    for t in times:
        gt=samp('translation',[0,0,0],t)*0.1; gt[0]=0; gt[2]=0   # strip horizontal root motion (in-place)
        gr=samp('rotation',[0,0,0,1],t); gr/=np.linalg.norm(gr)
        tt,qq=bake(gt,gr,aj['nodes'][anames.index('pelvis')]); T.append(tt); Q.append(qq)
    ii=add(times.astype(np.float32).tobytes(),5126,'SCALAR',len(times),[float(times.min())],[float(times.max())])
    for path,data,typ in [('translation',T,'VEC3'),('rotation',Q,'VEC4')]:
        oo=add(np.array(data,np.float32).tobytes(),5126,typ,len(times))
        sm.append({'input':ii,'output':oo,'interpolation':'LINEAR'}); ch.append({'sampler':len(sm)-1,'target':{'node':PEL,'path':path}})
    j['animations'].append({'name':nm,'channels':ch,'samplers':sm})
    disp=samp('translation',[0,0,0],times[-1])-samp('translation',[0,0,0],times[0])
    print(nm,'disp_m',(disp*0.1).round(2),'dur',times.max(),'frames',len(times),'ge y range',[round(float(x[1]),3) for x in (min(T,key=lambda v:v[1]),max(T,key=lambda v:v[1]))])
# --- textures: real skin diffuse + eye
def addimg(path,name):
    bio=io.BytesIO(); Image.open(path).convert('RGB').save(bio,'PNG'); d=bio.getvalue()
    while len(b)%4: b.append(0)
    j['bufferViews'].append({'buffer':0,'byteOffset':len(b),'byteLength':len(d)}); b.extend(d)
    return {'name':name,'mimeType':'image/png','bufferView':len(j['bufferViews'])-1}
skinpng=f'{PROJ}/assets/source/young_lightskinned_male_diffuse.png'
j['images']=[addimg(skinpng,'skin'),addimg(f'{PROJ}/assets/source/brown_eye.png','eye')]
for m in j['materials']: m['pbrMetallicRoughness'].update(metallicFactor=0.0,roughnessFactor=1.0)
j['buffers']=[{'byteLength':len(b)}]
js=json.dumps(j,separators=(',',':')).encode()
while len(js)%4: js+=b' '
while len(b)%4: b.append(0)
out=struct.pack('<III',0x46546C67,2,12+8+len(js)+8+len(b))+struct.pack('<II',len(js),0x4E4F534A)+js+struct.pack('<II',len(b),0x004E4942)+bytes(b)
open(f'{PROJ}/assets/models/gaelic_player.glb','wb').write(out); print('wrote',len(out))
# --- kit textures: paint UV islands by bind-pose body region
prim=j['meshes'][0]['primitives'][0]
pos=acc(j,b,prim['attributes']['POSITION']); uv=acc(j,b,prim['attributes']['TEXCOORD_0']); ind=acc(j,b,prim['indices'])[:,0].reshape(-1,3)
print('mesh bbox',pos.min(0),pos.max(0))
base=Image.open(skinpng).convert('RGB').resize((1024,1024)); S=1024
kits={'home':[(40,70,200),(250,215,30),(245,245,245),(40,70,200)],   # jersey A, hoop B, shorts, socks
      'away':[(200,20,40),(20,150,40),(30,30,30),(200,20,40)],
      'gk_home':[(20,170,90),(10,90,50),(20,20,20),(20,170,90)],      # keepers: distinct colours
      'gk_away':[(250,140,20),(30,30,30),(30,30,30),(250,140,20)],
      'referee':[(25,25,25),(230,200,0),(25,25,25),(25,25,25)],
      'umpire':[(250,250,250),(250,250,250),(250,250,250),(30,30,30)]}   # long white coat
for kname,(ja_,jb_,sh,so) in kits.items():
    im=base.copy(); dr=ImageDraw.Draw(im)
    for tri in ind:
        p=pos[tri].mean(0); y=p[1]; ax=abs(p[0])
        col=None
        if kname=='umpire' and 0.5<y<1.47 and ax<0.75: col=ja_   # coat incl. long sleeves
        elif 1.0<y<1.47 and ax<0.42: col = jb_ if 1.17<y<1.27 else ja_   # torso + short sleeves
        elif 0.72<y<=1.0 and ax<0.25: col=sh
        elif 0.1<y<0.45: col=so
        elif y<=0.1: col=(25,25,25)  # boots
        if col: dr.polygon([(float(u*S),float(v*S)) for u,v in uv[tri]],fill=col)
    im.save(f'{PROJ}/assets/textures/kit_{kname}.png')
print('kits done')
