from __future__ import annotations

import json
import pickle
import math
from collections import defaultdict, Counter
from pathlib import Path

import pandas as pd

REVIEWS_DIR = Path('/home/pi/.agents/skills/stock-select/runtime/reviews')
PREPARED_DIR = Path('/home/pi/.agents/skills/stock-select/runtime/prepared')
OUT = Path('/tmp/dribull_tuning_diag')
OUT.mkdir(parents=True, exist_ok=True)

FIELDS = ['trend_structure','price_position','volume_behavior','previous_abnormal_move','macd_phase']

LATEST_PREPARED = None

def load_prepared(date: str):
    global LATEST_PREPARED
    # Forward-return diagnostics need post-pick future bars; use latest shared cache,
    # not same-day cache, otherwise all April samples before month-end have no forward data.
    if LATEST_PREPARED is not None:
        return LATEST_PREPARED
    paths = sorted(PREPARED_DIR.glob('2026-04-*.pkl'))
    paths = [p for p in paths if not any(p.name.endswith(f'.{m}.pkl') for m in ['hcr'])]
    if not paths:
        return None
    payload = pickle.loads(paths[-1].read_bytes())
    LATEST_PREPARED = payload.get('prepared_by_symbol', payload)
    return LATEST_PREPARED

def forward(prepared, code, pick_date):
    hist = prepared.get(code)
    if hist is None:
        # try without suffix? unlikely
        hist = prepared.get(code.split('.')[0])
    if hist is None or len(hist) == 0:
        return None
    df = hist.copy()
    df['trade_date'] = pd.to_datetime(df['trade_date'], errors='coerce', format='mixed')
    df = df.sort_values('trade_date').reset_index(drop=True)
    for c in ['open','close']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    cutoff = pd.Timestamp(pick_date)
    cur = df[df.trade_date <= cutoff].tail(1)
    if cur.empty or pd.isna(cur.iloc[0]['close']):
        return None
    entry = float(cur.iloc[0]['close'])
    fut = df[df.trade_date > cutoff]
    ret = {'entry_close': entry}
    if len(fut) >= 3:
        ret['ret3_pct'] = (float(fut.iloc[2]['close']) / entry - 1) * 100
    else:
        ret['ret3_pct'] = None
    if len(fut) >= 5:
        ret['ret5_pct'] = (float(fut.iloc[4]['close']) / entry - 1) * 100
    else:
        ret['ret5_pct'] = None
    return ret

def get_score(item, field):
    if field in item:
        return item.get(field)
    br = item.get('baseline_review') or {}
    return br.get(field)

def get_verdict(item):
    v = item.get('verdict') or (item.get('baseline_review') or {}).get('verdict')
    return str(v or '').upper()

def get_code(item):
    return item.get('code') or item.get('ts_code') or item.get('symbol')

def pearson(xs, ys):
    pairs = [(float(x), float(y)) for x, y in zip(xs, ys) if x is not None and y is not None and math.isfinite(float(x)) and math.isfinite(float(y))]
    n = len(pairs)
    if n < 3:
        return None
    xbar = sum(x for x,_ in pairs)/n; ybar=sum(y for _,y in pairs)/n
    num=sum((x-xbar)*(y-ybar) for x,y in pairs)
    denx=math.sqrt(sum((x-xbar)**2 for x,_ in pairs)); deny=math.sqrt(sum((y-ybar)**2 for _,y in pairs))
    if denx == 0 or deny == 0:
        return None
    return num/(denx*deny)

def rankdata(vals):
    order=sorted(range(len(vals)), key=lambda i: vals[i])
    ranks=[0.0]*len(vals); i=0
    while i < len(order):
        j=i
        while j+1 < len(order) and vals[order[j+1]] == vals[order[i]]:
            j += 1
        avg=(i+j+2)/2.0
        for k in range(i,j+1): ranks[order[k]]=avg
        i=j+1
    return ranks

def spearman(xs, ys):
    pairs=[(float(x), float(y)) for x,y in zip(xs,ys) if x is not None and y is not None and math.isfinite(float(x)) and math.isfinite(float(y))]
    if len(pairs)<3: return None
    rx=rankdata([x for x,_ in pairs]); ry=rankdata([y for _,y in pairs])
    return pearson(rx, ry)

def stats(items, ret_key='ret3_pct'):
    vals=[r[ret_key] for r in items if r.get(ret_key) is not None and math.isfinite(float(r[ret_key]))]
    if not vals:
        return {'n':0}
    return {'n':len(vals),'avg':round(sum(vals)/len(vals),3),'median':round(float(pd.Series(vals).median()),3),'win_rate':round(sum(v>0 for v in vals)/len(vals)*100,1),'max':round(max(vals),3),'min':round(min(vals),3)}

def bucket_total(v):
    if v < 3.0: return '<3.0'
    if v < 3.2: return '3.0-3.2'
    if v < 3.5: return '3.2-3.5'
    if v < 3.8: return '3.5-3.8'
    if v < 4.0: return '3.8-4.0'
    if v < 4.2: return '4.0-4.2'
    if v < 4.5: return '4.2-4.5'
    return '>=4.5'

records=[]; missing=[]; dirs=[]
for sp in sorted(REVIEWS_DIR.glob('2026-04-*.dribull/summary.json')):
    date = sp.parent.name.split('.')[0]
    prepared = load_prepared(date)
    dirs.append(date)
    if prepared is None:
        missing.append({'date':date,'reason':'no_prepared'})
        continue
    summary=json.loads(sp.read_text())
    items=(summary.get('recommendations') or []) + (summary.get('excluded') or [])
    for item in items:
        code=get_code(item)
        if not code: continue
        fwd=forward(prepared, code, summary.get('pick_date', date))
        if fwd is None:
            missing.append({'date':date,'code':code,'reason':'no_fwd_frame'})
            continue
        row={'pick_date':summary.get('pick_date', date),'dir_date':date,'code':code,'name':item.get('name'), 'verdict':get_verdict(item)}
        for fld in FIELDS+['total_score']:
            val=get_score(item, fld)
            row[fld]=float(val) if val is not None else None
        row.update(fwd)
        records.append(row)

# dump csv/json
pd.DataFrame(records).to_csv(OUT/'records.csv', index=False)

corr=[]
for fld in ['total_score']+FIELDS:
    for ret in ['ret3_pct','ret5_pct']:
        xs=[r[fld] for r in records]; ys=[r[ret] for r in records]
        valid=sum(1 for x,y in zip(xs,ys) if x is not None and y is not None)
        corr.append({'field':fld,'ret':ret,'n':valid,'pearson':None if pearson(xs,ys) is None else round(pearson(xs,ys),4),'spearman':None if spearman(xs,ys) is None else round(spearman(xs,ys),4)})

layers={}
# verdict layers
layers['by_verdict']={v:{'ret3':stats([r for r in records if r['verdict']==v],'ret3_pct'),'ret5':stats([r for r in records if r['verdict']==v],'ret5_pct')} for v in sorted(set(r['verdict'] for r in records))}
# total bucket
order=['<3.0','3.0-3.2','3.2-3.5','3.5-3.8','3.8-4.0','4.0-4.2','4.2-4.5','>=4.5']
layers['by_total_bucket']={b:{'ret3':stats([r for r in records if bucket_total(r['total_score'])==b],'ret3_pct'),'ret5':stats([r for r in records if bucket_total(r['total_score'])==b],'ret5_pct')} for b in order}
# score value 1-5 rounded/exact
layers['by_field_score']={}
for fld in FIELDS:
    d={}
    for score in [1,2,3,4,5]:
        subset=[r for r in records if r[fld] is not None and int(round(r[fld]))==score]
        d[str(score)]={'ret3':stats(subset,'ret3_pct'),'ret5':stats(subset,'ret5_pct')}
    layers['by_field_score'][fld]=d

# top/bottom snippets
valid3=[r for r in records if r.get('ret3_pct') is not None]
worst=sorted(valid3, key=lambda r:r['ret3_pct'])[:20]
best=sorted(valid3, key=lambda r:r['ret3_pct'], reverse=True)[:20]

out={'summary':{'review_dirs':dirs,'review_dir_count':len(dirs),'records':len(records),'missing_count':len(missing),'verdict_counts':Counter(r['verdict'] for r in records)},'correlations':corr,'layers':layers,'best_ret3':best,'worst_ret3':worst,'missing_sample':missing[:20]}
(OUT/'diagnostics.json').write_text(json.dumps(out, ensure_ascii=False, indent=2))
print(json.dumps({'summary':out['summary'],'correlations':corr,'by_verdict':layers['by_verdict'],'by_total_bucket':layers['by_total_bucket']}, ensure_ascii=False, indent=2))
print('OUT', OUT)
