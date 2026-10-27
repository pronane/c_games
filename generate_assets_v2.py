"""
V2 HD sprite generator — fills canvas, CEL-shaded, black outlines, ground shadow.
Same 6 fighters, same 16 states, but fighters are BIG (70% canvas) and connected.
Run this to overwrite assets/ with the improved set (F2 will toggle to AI HD set).
"""
import json, math, os, pygame
pygame.init()
pygame.display.set_mode((1,1))

SCALE=2; BASE_W, BASE_H=96,128; GROUND_OFFSET=6; FPS=60
OUT=os.path.join(os.path.dirname(__file__),"assets")
SPR=os.path.join(OUT,"sprites"); STG=os.path.join(OUT,"stages"); FX=os.path.join(OUT,"fx"); SEL=os.path.join(OUT,"select")
for d in (OUT,SPR,STG,FX,SEL): os.makedirs(d,exist_ok=True)

C={"bg":(16,18,28),"skin_l":(245,210,175),"skin_m":(210,165,125),"skin_d":(170,125,90),
   "white":(238,238,244),"black":(18,18,22),"gray":(158,158,170),"red":(220,55,50),"blue":(60,115,220),
   "green":(75,195,95),"yellow":(255,220,80),"purple":(175,85,210),"orange":(255,140,45),"cyan":(110,210,255),"elec":(210,255,110)}

FIGHTERS={
 "kairo": {"name":"KAIRO","pal":dict(skin=C["skin_l"],skin_d=C["skin_m"], prim=C["red"], sec=C["black"], acc=C["yellow"], hair=C["black"], glove=C["white"], boot=C["black"], belt=C["yellow"]), "body":"lean","gear":"headband","outfit":"shorts","weapon":None,"fx":None},
 "lyra":  {"name":"LYRA","pal":dict(skin=C["skin_m"],skin_d=C["skin_d"], prim=C["cyan"], sec=C["white"], acc=C["green"], hair=C["purple"], glove=C["white"], boot=C["white"], belt=C["green"]), "body":"slim","gear":"none","outfit":"dojo","weapon":None,"fx":"aura"},
 "brutus":{"name":"BRUTUS","pal":dict(skin=C["skin_l"],skin_d=C["skin_m"], prim=C["gray"], sec=C["black"], acc=C["orange"], hair=C["black"], glove=C["gray"], boot=C["gray"], belt=C["black"]), "body":"heavy","gear":"none","outfit":"tank","weapon":None,"fx":None},
 "naomi": {"name":"NAOMI","pal":dict(skin=C["skin_l"],skin_d=C["skin_m"], prim=C["purple"], sec=C["white"], acc=C["red"], hair=C["black"], glove=C["white"], boot=C["black"], belt=C["red"]), "body":"slim","gear":"ribbon","outfit":"kimono","weapon":"katana","fx":None},
 "zap":   {"name":"ZAP","pal":dict(skin=C["skin_l"],skin_d=C["skin_m"], prim=C["blue"], sec=C["black"], acc=C["yellow"], hair=C["yellow"], glove=C["yellow"], boot=C["blue"], belt=C["yellow"]), "body":"lean","gear":"mask","outfit":"suit","weapon":None,"fx":"electric"},
 "void":  {"name":"VOID","pal":dict(skin=C["skin_d"],skin_d=C["black"], prim=C["black"], sec=C["cyan"], acc=C["elec"], hair=C["cyan"], glove=C["cyan"], boot=C["black"], belt=C["cyan"]), "body":"lean","gear":"hood","outfit":"robe","weapon":None,"fx":"void"},
}

def new_canvas(w=BASE_W,h=BASE_H):
    return pygame.Surface((w,h), pygame.SRCALPHA)
def rect(s,x,y,w,h,col):
    pygame.draw.rect(s,col,(x,y,w,h))
def rect_outline(s,x,y,w,h,col,border=1, fill=None):
    if fill: pygame.draw.rect(s,fill,(x,y,w,h))
    pygame.draw.rect(s,col,(x,y,w,h),border)
def ellipse(s,x,y,w,h,col,border=0):
    if border: pygame.draw.ellipse(s,col,(x,y,w,h),border)
    else: pygame.draw.ellipse(s,col,(x,y,w,h))
def line(s,x1,y1,x2,y2,col,w=3):
    pygame.draw.line(s,col,(x1,y1),(x2,y2),w)

def body_dims(body):
    if body=="heavy": return dict(neck=6, chest=26, waist=22, hips=24, arm_w=10, thigh_w=12, head_r=13, head_w=16, head_h=18)
    if body=="slim":  return dict(neck=4, chest=20, waist=16, hips=18, arm_w=7,  thigh_w=8,  head_r=11, head_w=13, head_h=15)
    return dict(neck=5, chest=23, waist=19, hips=21, arm_w=8, thigh_w=10, head_r=12, head_w=15, head_h=17)

def shade(col, k): return (max(0, int(col[0]*k)), max(0, int(col[1]*k)), max(0, int(col[2]*k)))
def hilite(col, k=1.15): return (min(255,int(col[0]*k)), min(255,int(col[1]*k)), min(255,int(col[2]*k)))

# --- draw a big filled body ---
def draw_fighter_frame(s, tag, char, state, frame_idx):
    p=char["pal"]; d=body_dims(char["body"])
    # layout: fill most of canvas — head top ~10, hips ~70, feet ~118
    cx=BASE_W//2
    # key y's in base coords
    head_cy = 22          # head center y
    neck_y  = head_cy+8
    chest_y = neck_y+2
    chest_h = 18
    waist_y = chest_y+chest_h
    waist_h = 8
    hips_y  = waist_y+waist_h
    thigh_top = hips_y+2
    knee_y  = 96
    feet_y  = BASE_H - GROUND_OFFSET  # ~122 but clamp to 118 for heavy
    if feet_y>118: feet_y=118

    # ground shadow (under feet)
    shadow_w = d["hips"]+8
    shadow = pygame.Surface((shadow_w*2, 10), pygame.SRCALPHA)
    pygame.draw.ellipse(shadow, (0,0,0,70), (0,0,shadow_w*2,10))
    if state in ("jump",): alpha=int(30+20*math.sin(frame_idx*0.8))
    else: alpha=70
    shadow.set_alpha(alpha)
    s.blit(shadow, (cx - shadow_w, feet_y+1))

    # ---- legs ----
    # thighs: tapered rects with outline
    for side in (-1,1):
        # swing for walk
        swing=0
        if state=="walk": swing=int(4*math.sin(frame_idx*0.9 + (0 if side==-1 else math.pi)))
        x0 = cx + side*(d["hips"]//2 -2)
        x1 = x0 + side*2
        x_ankle = x1 + swing*side
        # thigh
        thigh_col = p["prim"]
        # outline + fill
        pts_thigh=[(x0, thigh_top),(x0+side*d["thigh_w"], thigh_top),(x_ankle+side*d["thigh_w"]//2, knee_y),(x_ankle, knee_y)]
        # draw as thick line + rect for fill
        line(s, x0, thigh_top, x_ankle, knee_y, C["black"], d["thigh_w"]+2) # outline
        line(s, x0, thigh_top, x_ankle, knee_y, thigh_col, d["thigh_w"])
        # shin
        line(s, x_ankle, knee_y, x_ankle+ swing//2, feet_y, C["black"], 8)
        line(s, x_ankle, knee_y, x_ankle+ swing//2, feet_y, thigh_col, 6)
        # boot
        rect_outline(s, x_ankle-6, feet_y-4, 12, 6, C["black"], 1, p["boot"])

    # ---- shorts / hips band ----
    if char["outfit"]=="shorts":
        rect_outline(s, cx - d["hips"]//2, hips_y-4, d["hips"], 14, C["black"],1, p["prim"])
        # belt
        rect_outline(s, cx - d["waist"]//2, waist_y, d["waist"], 6, C["black"],1, p["belt"])
    elif char["outfit"]=="dojo":
        rect_outline(s, cx - d["chest"]//2 -2, chest_y-2, d["chest"]+4, 28, C["black"],1, p["sec"])
        rect_outline(s, cx - d["waist"]//2, waist_y, d["waist"], 6, C["black"],1, p["acc"])
        rect_outline(s, cx - d["hips"]//2, hips_y-2, d["hips"], 12, C["black"],1, p["sec"])
    elif char["outfit"]=="tank":
        rect_outline(s, cx - d["chest"]//2, chest_y-2, d["chest"], 26, C["black"],1, p["prim"])
        rect_outline(s, cx - d["waist"]//2, waist_y, d["waist"], 6, C["black"],1, p["sec"])
        rect_outline(s, cx - d["hips"]//2, hips_y-2, d["hips"], 12, C["black"],1, p["acc"] if tag=="brutus" else p["prim"])
    elif char["outfit"]=="kimono":
        rect_outline(s, cx - d["chest"]//2-3, chest_y-4, d["chest"]+6, 30, C["black"],1, p["sec"])
        rect_outline(s, cx - 6, waist_y+2, 12, 6, C["black"],1, p["prim"]) # obi
    elif char["outfit"]=="suit":
        rect_outline(s, cx - d["chest"]//2-2, chest_y-2, d["chest"]+4, 28, C["black"],1, p["sec"])
        rect_outline(s, cx - d["waist"]//2, waist_y, d["waist"], 6, C["black"],1, p["prim"])
        rect_outline(s, cx - d["hips"]//2, hips_y-2, d["hips"], 12, C["black"],1, p["acc"])
    else: # robe
        rect_outline(s, cx - d["chest"]//2-6, chest_y-4, d["chest"]+12, 32, C["black"],1, p["prim"])
        rect_outline(s, cx - d["waist"]//2, waist_y+4, d["waist"], 6, C["black"],1, p["acc"])

    # ---- chest / torso (on top of hips) ----
    # chest already drawn per outfit, add pec highlight
    # simple highlight line
    hl = hilite(p["sec"] if char["outfit"] in ("dojo","kimono","robe") else p["skin"],1.35)
    # skin visible for bare chest (shorts/tank)
    if char["outfit"] in ("shorts","tank"):
        rect_outline(s, cx - d["chest"]//2+2, chest_y+2, d["chest"]-4, chest_h-4, C["black"],1, p["skin"])
        # abs line
        line(s, cx, chest_y+10, cx, chest_y+18, shade(p["skin"],0.85), 1)

    # ---- neck ----
    rect_outline(s, cx - d["neck"]//2, neck_y-2, d["neck"], 5, C["black"],1, p["skin"])

    # ---- head ----
    hr=d["head_r"]; hx=cx; hy=head_cy
    # base head
    ellipse(s, hx - hr//2 -2, hy - hr//2 -4, hr+4, hr+6, p["skin"])
    pygame.draw.ellipse(s, C["black"], (hx - hr//2 -2, hy - hr//2 -4, hr+4, hr+6), 1)
    # hair / gear
    hair=p["hair"]
    if char["gear"]=="headband":
        rect_outline(s, hx- hr//2 -3, hy- hr//2 -6, hr+6, 5, C["black"],1, p["prim"])
        # hair top
        ellipse(s, hx-8, hy-10, 16, 10, hair)
    elif char["gear"]=="mask":
        rect_outline(s, hx- hr//2 -2, hy- hr//2 -2, hr+4, 5, C["black"],1, p["sec"])
        rect_outline(s, hx-6, hy-1, 12, 6, C["black"],1, p["sec"])
        ellipse(s, hx, hy-3, hr-4, hr-4, p["skin_d"])
    elif char["gear"]=="ribbon":
        rect_outline(s, hx- hr//2 -2, hy- hr//2 -7, hr+4, 5, C["black"],1, p["prim"])
        ellipse(s, hx, hy-2, hr-2, hr-1, p["skin"])
    elif char["gear"]=="hood":
        rect_outline(s, hx- hr//2 -6, hy- hr//2 -9, hr+12, 14, C["black"],1, p["sec"])
        ellipse(s, hx-4, hy-1, hr-3, hr-2, p["skin_d"])
    else:
        # normal hair cap
        ellipse(s, hx- hr//2 +1, hy- hr//2 -5, hr-2, 7, hair)

    # eyes
    eye_col = p["acc"] if char["fx"] in ("electric","void") else C["black"]
    line(s, hx-4, hy-1, hx-1, hy, eye_col, 2)
    line(s, hx+1, hy-1, hx+4, hy, eye_col, 2)
    # mouth (tiny)
    line(s, hx-1, hy+4, hx+1, hy+4, shade(p["skin"],0.6), 1)

    # ---- arms (state-driven, BIG) ----
    arm_y = chest_y + 6
    for side in (-1,1):
        # default idle pose parameters
        x_shoulder = cx + side*(d["chest"]//2 -2)
        if state=="idle":
            bob=int(2*math.sin(frame_idx*0.7))
            x_hand = x_shoulder + side*(6+bob)
            y_hand = arm_y+12+bob
            line(s, x_shoulder, arm_y, x_hand, y_hand, C["black"], d["arm_w"]+2)
            line(s, x_shoulder, arm_y, x_hand, y_hand, p["sec"] if char["outfit"] in ("dojo","robe") else p["skin"], d["arm_w"])
            rect_outline(s, x_hand-4, y_hand-3, 8, 7, C["black"],1, p["glove"])
        elif state=="walk":
            swing=int(5*math.sin(frame_idx*0.9 + (0 if side==-1 else math.pi)))
            x_hand = x_shoulder + side*(4+swing)
            y_hand = arm_y+10+abs(swing)//2
            line(s, x_shoulder, arm_y, x_hand, y_hand, C["black"], d["arm_w"]+2)
            line(s, x_shoulder, arm_y, x_hand, y_hand, p["skin"], d["arm_w"])
            rect_outline(s, x_hand-4, y_hand-3, 8,7, C["black"],1, p["glove"])
        elif state=="crouch":
            x_hand=cx+ side*10
            y_hand=waist_y+8
            line(s, x_shoulder, arm_y, x_hand, y_hand, C["black"], d["arm_w"]+2)
            line(s, x_shoulder, arm_y, x_hand, y_hand, p["prim"], d["arm_w"])
            rect_outline(s, x_hand-4, y_hand-3, 8,7, C["black"],1, p["glove"])
        elif state in ("lp",):
            if side==1:
                line(s, x_shoulder, arm_y, x_shoulder+side*(18+frame_idx*2), arm_y-1, C["black"], d["arm_w"]+2)
                line(s, x_shoulder, arm_y, x_shoulder+side*(18+frame_idx*2), arm_y-1, p["skin"], d["arm_w"])
                rect_outline(s, x_shoulder+side*(18+frame_idx*2)-4, arm_y-5, 9,9, C["black"],1, p["glove"])
            else:
                line(s, x_shoulder, arm_y, x_shoulder+side*6, arm_y+10, C["black"], d["arm_w"]+2)
                line(s, x_shoulder, arm_y, x_shoulder+side*6, arm_y+10, p["skin"], d["arm_w"])
                rect_outline(s, x_shoulder+side*6-4, arm_y+7, 8,7, C["black"],1, p["glove"])
        elif state=="hp":
            reach=12 if frame_idx<2 else (28 if frame_idx==2 else 10)
            step=6 if frame_idx>=2 else 0
            off=step* (1 if side==1 else -1)
            if side==1:
                line(s, x_shoulder+off, arm_y, x_shoulder+off+side*(16+reach), arm_y-5+frame_idx, C["black"], d["arm_w"]+3)
                line(s, x_shoulder+off, arm_y, x_shoulder+off+side*(16+reach), arm_y-5+frame_idx, p["skin"], d["arm_w"]+1)
                rect_outline(s, x_shoulder+off+side*(16+reach)-4, arm_y-9+frame_idx, 11,11, C["black"],1, p["glove"])
            else:
                line(s, x_shoulder, arm_y, x_shoulder+side*8, arm_y+10, C["black"], d["arm_w"]+2)
                line(s, x_shoulder, arm_y, x_shoulder+side*8, arm_y+10, p["skin"], d["arm_w"])
                rect_outline(s, x_shoulder+side*8-4, arm_y+7, 8,7, C["black"],1, p["glove"])
        elif state=="lk":
            x_hand=cx+ side*8
            y_hand=waist_y+10 if side==-1 else arm_y+10
            line(s, x_shoulder, arm_y, x_hand, y_hand, C["black"], d["arm_w"]+2)
            line(s, x_shoulder, arm_y, x_hand, y_hand, p["skin"], d["arm_w"])
            rect_outline(s, x_hand-4, y_hand-3, 8,7, C["black"],1, p["glove"])
        elif state=="hk":
            kick=18 if frame_idx<2 else (8 if frame_idx==2 else 0)
            if side==1:
                # extended leg-like kick with arm
                line(s, x_shoulder, arm_y, x_shoulder+side*(12+kick), arm_y-10, C["black"], d["arm_w"]+2)
                line(s, x_shoulder, arm_y, x_shoulder+side*(12+kick), arm_y-10, p["skin"], d["arm_w"])
                rect_outline(s, x_shoulder+side*(12+kick)-4, arm_y-14, 10,9, C["black"],1, p["glove"])
            else:
                line(s, x_shoulder, arm_y, x_shoulder+side*6, arm_y+10, C["black"], d["arm_w"]+2)
                line(s, x_shoulder, arm_y, x_shoulder+side*6, arm_y+10, p["skin"], d["arm_w"])
                rect_outline(s, x_shoulder+side*6-4, arm_y+7, 8,7, C["black"],1, p["glove"])
        elif state=="block":
            # forearms crossed in front
            line(s, x_shoulder, arm_y+6, cx-6, chest_y+12, C["black"], d["arm_w"]+2)
            line(s, x_shoulder, arm_y+6, cx-6, chest_y+12, p["skin"], d["arm_w"])
            line(s, cx+ d["chest"]//2-2, arm_y+6, cx+6, chest_y+12, C["black"], d["arm_w"]+2)
            line(s, cx+ d["chest"]//2-2, arm_y+6, cx+6, chest_y+12, p["skin"], d["arm_w"])
            if side==-1: rect_outline(s, cx-10, chest_y+8, 9,9, C["black"],1, p["glove"])
            else: rect_outline(s, cx+1, chest_y+8, 9,9, C["black"],1, p["glove"])
        elif state=="throw":
            grab=14 if frame_idx<2 else 6
            if side==1:
                line(s, x_shoulder, arm_y, x_shoulder+side*(14+grab), arm_y+1, C["black"], d["arm_w"]+3)
                line(s, x_shoulder, arm_y, x_shoulder+side*(14+grab), arm_y+1, p["skin"], d["arm_w"]+1)
                rect_outline(s, x_shoulder+side*(14+grab)-4, arm_y-3, 10,10, C["black"],1, p["glove"])
        elif state=="special1":
            if side==1:
                line(s, x_shoulder, arm_y, x_shoulder+side*20, arm_y+2, C["black"], d["arm_w"]+2)
                line(s, x_shoulder, arm_y, x_shoulder+side*20, arm_y+2, p["acc"], d["arm_w"])
                rect_outline(s, x_shoulder+side*20-4, arm_y-2, 10,10, C["black"],1, p["glove"])
            else:
                line(s, x_shoulder, arm_y, x_shoulder+side*6, arm_y+10, C["black"], d["arm_w"]+2)
                line(s, x_shoulder, arm_y, x_shoulder+side*6, arm_y+10, p["skin"], d["arm_w"])
                rect_outline(s, x_shoulder+side*6-4, arm_y+7, 8,7, C["black"],1, p["glove"])
        elif state=="special2":
            line(s, x_shoulder, arm_y, x_shoulder- side*6, arm_y+8, C["black"], d["arm_w"]+2)
            line(s, x_shoulder, arm_y, x_shoulder- side*6, arm_y+8, p["prim"], d["arm_w"])
            rect_outline(s, x_shoulder- side*6 -4, arm_y+5, 9,9, C["black"],1, p["glove"])
        elif state=="super":
            line(s, x_shoulder, arm_y, x_shoulder+side*8, arm_y+14, C["black"], d["arm_w"]+2)
            line(s, x_shoulder, arm_y, x_shoulder+side*8, arm_y+14, p["acc"], d["arm_w"])
            rect_outline(s, x_shoulder+side*8-4, arm_y+11, 8,7, C["black"],1, p["glove"])
        elif state in ("hit",):
            line(s, x_shoulder, arm_y, x_shoulder+side*8, arm_y+10, C["black"], d["arm_w"]+2)
            line(s, x_shoulder, arm_y, x_shoulder+side*8, arm_y+10, p["skin"], d["arm_w"])
            rect_outline(s, x_shoulder+side*8-4, arm_y+7, 8,7, C["black"],1, p["glove"])
        else: # win/lose etc
            line(s, x_shoulder, arm_y, x_shoulder+side*6, arm_y+12, C["black"], d["arm_w"]+2)
            line(s, x_shoulder, arm_y, x_shoulder+side*6, arm_y+12, p["skin"], d["arm_w"])
            rect_outline(s, x_shoulder+side*6-4, arm_y+9, 8,7, C["black"],1, p["glove"])

    # legs already done, but handle special2 dash offset and jump crouch tweaks
    if state=="jump":
        # tuck legs
        pass
    # weapon: katana for naomi
    if char["weapon"]=="katana" and state in ("idle","lp","hp","special1","walk","hk","super"):
        bx = cx + (d["chest"]//2 -2) + (4 if state=="hp" and frame_idx==2 else 0)
        by = chest_y+4
        ex = bx + 18 + (10 if state=="hp" and frame_idx==2 else 0)
        ey = by - 8 - (6 if state=="special1" else 0)
        line(s, bx, by, ex, ey, C["white"], 3)
        line(s, bx, by, ex, ey, shade(C["white"],0.85), 1)
        rect_outline(s, bx-2, by-1, 6,3, C["black"],1, C["gray"])

    # fx aura etc
    fx=char["fx"]
    if fx=="aura" and state in ("idle","walk","special1","super"):
        glow_r=8+int(2*math.sin(frame_idx*0.9))
        aura=pygame.Surface((glow_r*2+6, glow_r*2+6), pygame.SRCALPHA)
        pygame.draw.ellipse(aura, (*p["acc"],60), (0,0,glow_r*2+6, glow_r*2+6))
        s.blit(aura,(cx - glow_r -3, chest_y-6))
    if fx=="electric" and state in ("idle","special1","super","throw","lp"):
        for k in range(3):
            a=math.radians(frame_idx*70 + k*120)
            ex=cx+ math.cos(a)*(10+frame_idx%4)
            ey=chest_y+ math.sin(a)*7
            line(s, cx, chest_y+6, ex, ey, p["acc"], 1)
    if fx=="void" and state in ("special2","super"):
        pygame.draw.circle(s, p["acc"], (cx, chest_y+4), 6+frame_idx%3, 2)
        pygame.draw.circle(s, C["white"], (cx, chest_y+4), 2)

STATES={"idle":(5,6),"walk":(7,4),"crouch":(2,8),"jump":(5,5),"lp":(4,3),"hp":(5,4),"lk":(4,3),"hk":(5,4),"block":(2,8),"throw":(5,4),"special1":(6,4),"special2":(5,3),"super":(7,4),"hit":(3,5),"win":(5,6),"lose":(3,8)}
def build_character(tag,char):
    meta={}; d=body_dims(char["body"])
    for state,(frames,dur) in STATES.items():
        strip=pygame.Surface((BASE_W*frames, BASE_H), pygame.SRCALPHA)
        strip.fill((0,0,0,0))
        for i in range(frames):
            s=new_canvas()
            # slightly bob for idle
            dy=int(1*math.sin(i*0.9)) if state=="idle" else 0
            # draw into temp then blit with dy
            tmp=new_canvas()
            draw_fighter_frame(tmp, tag, char, state, i)
            strip.blit(tmp,(i*BASE_W, dy))
        path=os.path.join(SPR, f"{tag}_{state}.png")
        big=pygame.transform.scale(strip,(strip.get_width()*SCALE, strip.get_height()*SCALE))
        pygame.image.save(big, path)
        meta[state]=[f"sprites/{tag}_{state}.png", frames, dur]
    return meta

meta={"characters":{},"stages":[],"effects":{},"select":{}}
for tag,char in FIGHTERS.items():
    meta["characters"][tag]=build_character(tag,char)
    print(f"generated {tag}")

def save_sheet(name, surf, folder=FX, do_scale=True):
    if do_scale:
        big=pygame.transform.scale(surf,(surf.get_width()*SCALE, surf.get_height()*SCALE))
        pygame.image.save(big, os.path.join(folder,name))
    else:
        pygame.image.save(surf, os.path.join(folder,name))

def fireball_strip(name, col, count=6, size=40):
    strip=new_canvas(size*count,size); strip.fill((0,0,0,0))
    for i in range(count):
        s=new_canvas(size,size); s.fill((0,0,0,0))
        r=9+int(3*math.sin(i*0.9)); cx=size//2; cy=size//2
        for rr in range(r,2,-2):
            shade_v=max(60,255-rr*12); col_v=(min(255,shade_v+40), min(255,shade_v+80), 140)
            pygame.draw.ellipse(s,col_v,(cx-rr,cy-rr,rr*2,rr*2))
        strip.blit(s,(i*size,0))
    save_sheet(name,strip, FX); return [f"fx/{name}",count,3]
def spark_strip(name,col,count=4,size=28):
    strip=new_canvas(size*count,size); strip.fill((0,0,0,0))
    for i in range(count):
        s=new_canvas(size,size); s.fill((0,0,0,0))
        cx,cy=size//2,size//2
        for k in range(6):
            a=math.radians(k*60 + i*15); ex=cx+math.cos(a)*11; ey=cy+math.sin(a)*11
            pygame.draw.line(s,col,(cx,cy),(ex,ey),2)
        pygame.draw.circle(s,C["white"],(cx,cy),3)
        strip.blit(s,(i*size,0))
    save_sheet(name,strip, FX); return [f"fx/{name}",count,2]
def flash_strip(name,col,size=100):
    s=new_canvas(size,size); s.fill((0,0,0,0))
    pygame.draw.circle(s,(*col[:3],140),(size//2,size//2), size//2-6)
    pygame.draw.circle(s,C["white"],(size//2,size//2), size//4)
    save_sheet(name,s, FX, do_scale=False); return [f"fx/{name}",1,3]

meta["effects"]["fireball"]=fireball_strip("fireball.png", C["red"])
meta["effects"]["elecball"]=fireball_strip("elecball.png", C["yellow"])
meta["effects"]["spark"]=spark_strip("spark.png", C["yellow"])
meta["effects"]["block_spark"]=spark_strip("block_spark.png", C["white"])
meta["effects"]["hit_flash"]=flash_strip("hit_flash.png", C["red"])
meta["effects"]["super_flash"]=flash_strip("super_flash.png", C["cyan"])

W,H=1280,720
def save_stage(name,surf,folder=STG):
    pygame.image.save(surf, os.path.join(folder,name))
def stage_rooftop():
    bg=pygame.Surface((W,H))
    for y in range(H):
        t=y/H; col=(int(8+12*t), int(10+16*t), int(18+32*t))
        pygame.draw.line(bg,col,(0,y),(W,y))
    pygame.draw.circle(bg,(232,232,240),(1080,96),46); pygame.draw.circle(bg,(26,28,42),(1100,88),10)
    for x,y,w,h in [(90,320,150,260),(290,360,130,220),(510,300,190,300),(750,340,150,240),(950,320,170,280),(1130,380,110,200)]:
        pygame.draw.rect(bg,(14,16,24),(x,y,w,h)); pygame.draw.rect(bg,(22,24,34),(x,y,w,3))
        for wy in range(y+18, y+h-20, 20):
            for wx in range(x+14, x+w-14, 18):
                if (wx*3+wy*5)%23==0: pygame.draw.rect(bg,(255,215,145),(wx,wy,10,12))
    save_stage("stage_rooftop_bg.png",bg)
    mid=pygame.Surface((W,H), pygame.SRCALPHA); mid.fill((0,0,0,0))
    pygame.draw.rect(mid,(36,38,52),(0,H-240,W,240)); pygame.draw.rect(mid,(66,70,86),(0,H-240,W,6))
    for i in range(0,W,38): pygame.draw.rect(mid,(148,148,156),(i,H-264,5,24))
    for bx,by,col in [(300,H-164,(255,45,120)),(690,H-146,(0,235,190)),(990,H-126,(255,235,45))]:
        pygame.draw.rect(mid,(*col,90),(bx-6,by-6,132,36), border_radius=6)
        pygame.draw.rect(mid,col,(bx,by,120,24), border_radius=4)
        # kanji
        pygame.draw.rect(mid,(22,22,28),(bx+36,by+6,48,14))
    save_stage("stage_rooftop_mid.png",mid)
    fg=pygame.Surface((W,H), pygame.SRCALPHA); fg.fill((0,0,0,0))
    for i in range(70):
        rx=(i*97+100)%W; ry=(i*53)%H
        pygame.draw.line(fg,(175,195,255,95),(rx,ry),(rx+2,ry+11),1)
    # puddle reflections
    for bx,col in [(300,(255,45,120)),(690,(0,235,190)),(990,(255,235,45))]:
        pygame.draw.ellipse(fg,(*col,28),(bx-10,H-22,140,10))
    save_stage("stage_rooftop_fg.png",fg)
def stage_temple():
    bg=pygame.Surface((W,H))
    for y in range(H):
        t=y/H; col=(int(248 -86*t), int(208-74*t), int(138-56*t))
        pygame.draw.line(bg,col,(0,y),(W,y))
    pygame.draw.polygon(bg,(178,140,98),[(0,H-240),(290,H-440),(610,H-240)])
    pygame.draw.polygon(bg,(148,112,76),[(500,H-240),(840,H-520),(1280,H-240)])
    pygame.draw.polygon(bg,(160,128,90),[(1000,H-240),(1140,H-380),(1280,H-240)])
    save_stage("stage_temple_bg.png",bg)
    mid=pygame.Surface((W,H), pygame.SRCALPHA); mid.fill((0,0,0,0))
    pygame.draw.rect(mid,(214,184,132),(0,H-240,W,240)); pygame.draw.rect(mid,(154,122,82),(0,H-240,W,6))
    for i in range(0,W,44): pygame.draw.rect(mid,(198,166,114),(i,H-236,40,3))
    for lx in (240,640,1040):
        pygame.draw.rect(mid,(120,82,54),(lx-10, H-300+30, 20, 120))
        pygame.draw.ellipse(mid,(255,172,102),(lx-24, H-300+12, 68, 46))
        pygame.draw.ellipse(mid,(255,228,188),(lx-16, H-300+18, 52, 34))
        pygame.draw.rect(mid,(40,28,18),(lx-1, H-300+34, 2, 8))
    # torii
    pygame.draw.rect(mid,(148,32,32),(480,H-320,W-960,14)); pygame.draw.rect(mid,(148,32,32),(520,H-320+28,W-1040,10))
    for x in (500, W-500): pygame.draw.rect(mid,(96,24,24),(x,H-320,14,80))
    # cherry blossom tree
    pygame.draw.rect(mid,(92,44,52),(250, H-220, 12, 100))
    pygame.draw.circle(mid,(220,140,160),(244, H-260),28); pygame.draw.circle(mid,(232,160,176),(258, H-274),32); pygame.draw.circle(mid,(210,120,144),(262, H-248),22)
    save_stage("stage_temple_mid.png",mid)
    fg=pygame.Surface((W,H), pygame.SRCALPHA); fg.fill((0,0,0,0))
    for i in range(50):
        px=(i*131+150)%W; py=(i*47+20)%H
        pygame.draw.circle(fg,(236,108,142,90),(px,py),3)
        pygame.draw.circle(fg,(255,182,200,60),(px+2,py+6),2)
    save_stage("stage_temple_fg.png",fg)
def stage_industrial():
    bg=pygame.Surface((W,H))
    for y in range(H):
        t=y/H; col=(int(18+16*t), int(20+18*t), int(28+30*t))
        pygame.draw.line(bg,col,(0,y),(W,y))
    for sx in (150,420,880,1120):
        pygame.draw.rect(bg,(42,44,54),(sx,H-360,24,360)); pygame.draw.rect(bg,(62,66,78),(sx,H-360,24,6))
        for y in (H-300, H-240, H-180): pygame.draw.rect(bg,(255,210,90),(sx+6, y, 8, 14))
        pygame.draw.ellipse(bg,(60,64,78,40),(sx-8, H-360-10,40,14))
    save_stage("stage_industrial_bg.png",bg)
    mid=pygame.Surface((W,H), pygame.SRCALPHA); mid.fill((0,0,0,0))
    pygame.draw.rect(mid,(56,58,70),(0,H-240,W,240)); pygame.draw.rect(mid,(94,98,114),(0,H-240,W,6))
    for i in range(0,W,60): pygame.draw.rect(mid,(124,128,144),(i,H-236,56,3))
    # pipes
    pygame.draw.line(mid,(102,106,122),(60,H-240),(60,H-120),7); pygame.draw.line(mid,(102,106,122),(60,H-240),(160,H-240),7)
    pygame.draw.line(mid,(102,106,122),(900,H-240),(900,H-100),7); pygame.draw.line(mid,(102,106,122),(900,H-180),(1000,H-180),6)
    # crane
    pygame.draw.line(mid,(142,146,162),(300,H-300),(300,H-240),7); pygame.draw.line(mid,(142,146,162),(300,H-300),(520,H-264),7)
    pygame.draw.rect(mid,(190,40,40),(306,H-300-18,28,18), border_radius=3)
    save_stage("stage_industrial_mid.png",mid)
    fg=pygame.Surface((W,H), pygame.SRCALPHA); fg.fill((0,0,0,0))
    for i in range(24):
        px=(i*200+100)%W; pygame.draw.rect(fg,(84,88,104,90),(px,H-42,44,6))
        pygame.draw.ellipse(fg,(0,0,0,18),(px-6,H-46,56,10))
    save_stage("stage_industrial_fg.png",fg)

stage_rooftop(); stage_temple(); stage_industrial()
meta["stages"]=[{"id":"rooftop","name":"NEON ROOFTOP","bg":"stages/stage_rooftop_bg.png","mid":"stages/stage_rooftop_mid.png","fg":"stages/stage_rooftop_fg.png"},
                {"id":"temple","name":"ANCIENT TEMPLE","bg":"stages/stage_temple_bg.png","mid":"stages/stage_temple_mid.png","fg":"stages/stage_temple_fg.png"},
                {"id":"industrial","name":"INDUSTRIAL ZONE","bg":"stages/stage_industrial_bg.png","mid":"stages/stage_industrial_mid.png","fg":"stages/stage_industrial_fg.png"}]

def draw_portrait(tag,char):
    s=pygame.Surface((128,128), pygame.SRCALPHA)
    p=char["pal"]
    # frame
    pygame.draw.rect(s,(24,28,40),(0,0,128,128), border_radius=10)
    pygame.draw.rect(s,p["prim"],(3,3,122,122), border_radius=9)
    pygame.draw.rect(s,(16,18,28),(6,6,116,116), border_radius=7)
    # draw chibi fighter
    d=body_dims(char["body"])
    cx,cy=64, 66
    # quick mini body
    # head
    hx,hy=cx,28
    pygame.draw.circle(s, p["skin"], (hx,hy), 14); pygame.draw.circle(s, C["black"], (hx,hy), 14, 2)
    # hair
    if char["gear"]=="headband": pygame.draw.rect(s, p["prim"], (hx-10, hy-12,20,5))
    elif char["gear"]=="hood": pygame.draw.rect(s, p["sec"], (hx-12, hy-14,24,14))
    elif char["gear"]=="mask": pygame.draw.rect(s, p["sec"], (hx-10, hy-8,20,6))
    pygame.draw.circle(s, p["skin"], (hx,hy), 2) # nose
    pygame.draw.line(s, C["black"], (hx-4,hy-1),(hx-1,hy),2); pygame.draw.line(s, C["black"], (hx+1,hy-1),(hx+4,hy),2)
    # torso
    pygame.draw.rect(s, p["prim"] if char["outfit"]=="shorts" else p["sec"], (cx-14,46,28,22))
    pygame.draw.rect(s, C["black"], (cx-14,46,28,22),1)
    pygame.draw.rect(s, p["belt"], (cx-10,68,20,5))
    # legs
    pygame.draw.rect(s, p["prim"], (cx-9,73,8,14)); pygame.draw.rect(s, p["prim"], (cx+1,73,8,14))
    pygame.draw.rect(s, p["boot"], (cx-10,84,10,6)); pygame.draw.rect(s, p["boot"], (cx+1,84,10,6))
    # name bar
    pygame.draw.rect(s,(10,12,18),(10,106,108,16), border_radius=4)
    path=os.path.join(SEL, f"portrait_{tag}.png")
    pygame.image.save(s, path)
    meta["select"][tag]=f"select/portrait_{tag}.png"

for tag,char in FIGHTERS.items(): draw_portrait(tag,char)
with open(os.path.join(OUT,"meta.json"),"w") as fh: json.dump(meta,fh,indent=2)
print("meta.json written")
pygame.quit()
