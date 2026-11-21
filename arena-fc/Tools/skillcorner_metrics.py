import json, sys, math, statistics as st
OD='/home/claude/skillcorner/opendata/data/matches/'
def pct(a,p): a=sorted(a); return a[int(p*(len(a)-1))] if a else float('nan')
def analyse(mid):
    meta=json.load(open(OD+f'{mid}/{mid}_match.json'))
    team={p['id']:p['team_id'] for p in meta['players']}
    gk={p['id'] for p in meta['players'] if p['player_role']['acronym']=='GK'}
    home=meta['home_team']['id']
    L={'in':[], 'out':[]}; W={'in':[], 'out':[]}; line=[]; press=[]; speeds=[]; prev={}
    for i,ln in enumerate(open(f'/tmp/sc/{mid}.jsonl')):
        fr=json.loads(ln)
        if fr['period'] is None: prev={}; continue
        pos={p['player_id']:(p['x'],p['y']) for p in fr['player_data']}
        # speeds (10 Hz)
        for pid,(x,y) in pos.items():
            if pid in prev and pid not in gk:
                px,py=prev[pid]; v=math.hypot(x-px,y-py)/0.1
                if v<12: speeds.append(v)
        prev=pos
        poss=fr['possession']; holder=poss.get('player_id'); grp=poss.get('group')
        if grp not in ('home team','away team'): continue
        if i%5: continue        # shape at 2 Hz
        in_team = home if grp=='home team' else [t for t in set(team.values()) if t!=home][0]
        for t in set(team.values()):
            xs=[pos[p][0] for p in pos if team.get(p)==t and p not in gk]
            ys=[pos[p][1] for p in pos if team.get(p)==t and p not in gk]
            if len(xs)<8: continue
            k='in' if t==in_team else 'out'
            L[k].append(max(xs)-min(xs)); W[k].append(max(ys)-min(ys))
            if k=='out':
                # defending direction: own goal side = the side where this team's GK stands
                g=[pos[p][0] for p in pos if p in gk and team.get(p)==t]
                if g: line.append(min(abs(x-g[0]) for x in xs))
        if holder in pos:
            hx,hy=pos[holder]; ht=team.get(holder)
            d=[math.hypot(pos[p][0]-hx,pos[p][1]-hy) for p in pos if team.get(p)!=ht and p not in gk]
            if d: press.append(min(d))
    return dict(length_in=st.median(L['in']), length_out=st.median(L['out']), width_in=st.median(W['in']), width_out=st.median(W['out']),
                def_line_from_gk=st.median(line), press_median=st.median(press), press_under2m=sum(x<2 for x in press)/len(press),
                speed_mean=st.mean(speeds), share_over_5_5=sum(v>5.5 for v in speeds)/len(speeds), share_over_7=sum(v>7 for v in speeds)/len(speeds), speed_p95=pct(speeds,.95))
res={m:analyse(m) for m in ('1925299','1996435','2011166')}
keys=list(next(iter(res.values())).keys())
avg={k:round(st.mean(r[k] for r in res.values()),3) for k in keys}
for m,r in res.items(): print(m, {k:round(v,2) for k,v in r.items()})
print('AVG', avg)
json.dump(dict(source='SkillCorner open data (MIT), A-League 2024/25 broadcast tracking', matches=list(res), per_match=res, average=avg), open('/home/claude/sc_ana/real_metrics.json','w'), indent=1)
