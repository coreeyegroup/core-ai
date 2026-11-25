#!/usr/bin/env python3
"""Offline quantitative utilities from pinned upstream source."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

import manager

PYTHON="python:3.12-slim"
QUANT="core-ai-lab-quant:0.1.0"
REDDY="reddygopalkrishna/trading-skills"
AGI="agiprolabs/claude-trading-skills"
STASKH="staskh/trading_skills"
PINS={REDDY:"df92aab5437202810a8fc1a7b666d35c539e0b63",AGI:"981e1d736cdc02bdc1c55c74ec9224e956414706",STASKH:"b025c283f16d6c49344d00e384b4b0cc347546da"}

def recipe(repo,entry,runtime,fields,fixture,body,check):
    return dict(repo=repo,entry=entry,runtime=runtime,fields=fields,fixture=fixture,body=body,check=check)

RECIPES={
 "technical-indicators":recipe(REDDY,"core/tradekit/indicators.py",PYTHON,
    "[closes,period]",[[1,2,3,4,5],3],
    "result={k:m[k](a[0],a[1]) for k in ('sma','ema','rsi')}",
    "assert result['sma']==[None,None,2,3,4];assert result['ema']==[None,None,2,3,4];close(result['rsi'][-1],100)"),
 "monte-carlo":recipe(REDDY,"core/tradekit/montecarlo.py",PYTHON,
    "[R multiples,risk_percent,trades,simulations,start_equity,seed]",[[1]*5,1,5,20,10000,7],
    """result=m['simulate_trades'](a[0],risk_pct=a[1],n_trades=a[2],n_sims=a[3],start_equity=a[4],seed=a[5])
result.pop('sample_paths',None)""",
    "close(result['final_return_pct'][50],5.10);close(result['prob_loss_pct'],0);close(result['risk_of_ruin_pct'],0)"),
 "numpy-drawdown":recipe(AGI,"skills/risk-management/scripts/drawdown_analyzer.py",QUANT,
    "[positive equity values]",[100,120,90,110,130],
    """import numpy as np
from dataclasses import asdict
result=asdict(m['analyze_drawdowns'](np.asarray(a,dtype=float)))""",
    "close(result['max_drawdown'],.25);close(result['current_drawdown'],0);assert result['num_drawdowns']==1"),
 "correlation-matrix":recipe(AGI,"skills/correlation-analysis/scripts/correlation_matrix.py",QUANT,
    "[aligned asset return series, ...]",[[1,2,3,4],[2,4,6,8],[4,3,2,1]],
    """import pandas as pd
frame=pd.DataFrame({str(i):v for i,v in enumerate(a)})
p,s=m['compute_correlation_matrices'](frame)
result={'pearson':p.to_dict(),'spearman':s.to_dict()}""",
    "close(result['pearson']['0']['1'],1);close(result['pearson']['0']['2'],-1);close(result['spearman']['0']['2'],-1)"),
 "scipy-option-price":recipe(STASKH,"src/trading_skills/black_scholes.py",QUANT,
    "[spot,strike,years,rate,volatility,dividend_yield]",[100,100,1,.05,.2,0],
    "result={k:m['black_scholes_price'](*a[:5],k,a[5]) for k in ('call','put')}",
    "close(result['call'],10.450583572185565);close(result['put'],5.573526022256971)"),
 "ema-backtest":recipe(AGI,"skills/backtrader/scripts/backtest_strategy.py",QUANT,
    "[fast,slow,cash,commission,slippage,fixed_units,seed,synthetic_days,OHLCV rows or []]",[3,8,10000,.001,.001,1,42,120,[]],
    """import backtrader as bt
import pandas as pd
fast,slow,cash,fee,slip,units,seed,days,rows=a
if rows:
    df=pd.DataFrame(rows,columns=['date','open','high','low','close','volume'])
    df.index=pd.to_datetime(df.pop('date'),utc=True).dt.tz_convert(None)
else:
    df=m['generate_synthetic_ohlcv'](days=days,seed=seed)
c=bt.Cerebro(stdstats=False)
c.adddata(bt.feeds.PandasData(dataname=df))
c.addstrategy(m['EMACrossoverStrategy'],fast_period=fast,slow_period=slow,printlog=False)
c.broker.setcash(cash)
c.broker.setcommission(commission=fee)
c.broker.set_slippage_perc(slip)
c.addsizer(bt.sizers.FixedSize,stake=units)
c.addanalyzer(bt.analyzers.DrawDown,_name='dd')
s=c.run()[0]
end=c.broker.getvalue()
result={'source':'provided' if rows else 'synthetic','bars':len(df),'initial_cash':cash,'final_value':end,'return_pct':100*(end/cash-1),'closed_trades':s.trade_count,'max_drawdown_pct':s.analyzers.dd.get_analysis()['max']['drawdown'],'open_units':s.position.size,'trade_log':s.trade_log}""",
    "assert result['bars']==120;assert result['closed_trades']>0;assert math.isfinite(result['final_value']);assert result['max_drawdown_pct']>=0")
}

PREFIX="""import json,math,sys
a=json.loads(''.join(sys.argv[2:]))
if sys.argv[1]=='core/tradekit/montecarlo.py':
    sys.path.insert(0,'core')
    from tradekit import montecarlo
    m=vars(montecarlo)
else:
    import importlib.util
    spec=importlib.util.spec_from_file_location('core_lab_upstream',sys.argv[1])
    mod=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=mod
    spec.loader.exec_module(mod)
    m=vars(mod)
def close(x,y):
    if not math.isclose(x,y,rel_tol=1e-7,abs_tol=1e-7):
        raise SystemExit('Unexpected fixture result: %r != %r'%(x,y))
"""

def number(v):
    return type(v) in (float,int) and abs(v)<=1e12 and math.isfinite(v)

def series(v,minimum=2,maximum=1000,positive=False):
    return isinstance(v,list) and minimum<=len(v)<=maximum and all(number(x) and (not positive or x>0) for x in v)

def validate(name,a):
    if not isinstance(a,list):
        raise ValueError("Use a JSON array")
    ok=False
    if name=="technical-indicators":
        ok=len(a)==2 and series(a[0],3,1000,True) and type(a[1]) is int and 1<=a[1]<len(a[0])
    elif name=="monte-carlo":
        ok=(len(a)==6 and series(a[0],5,500) and all(number(x) for x in a[1:]) and
            0<a[1]<=5 and type(a[2]) is int and 1<=a[2]<=500 and type(a[3]) is int and 1<=a[3]<=2000 and
            a[4]>0 and type(a[5]) is int and all(-10<=x<=10 for x in a[0]))
    elif name=="numpy-drawdown":
        ok=series(a,2,1000,True)
    elif name=="correlation-matrix":
        ok=(2<=len(a)<=8 and all(series(v,3,500) and len(set(v))>1 for v in a) and len({len(v) for v in a})==1)
    elif name=="scipy-option-price":
        ok=len(a)==6 and all(number(x) for x in a) and a[0]>0 and a[1]>0 and 0<a[2]<=100 and -1<=a[3]<=1 and 0<a[4]<=5 and -1<=a[5]<=1
    else:
        ok=(len(a)==9 and all(number(x) for x in a[:8]) and type(a[0]) is int and type(a[1]) is int
            and 1<=a[0]<a[1]<=100 and a[2]>0 and 0<=a[3]<.1 and 0<=a[4]<.1 and type(a[5]) is int and 1<=a[5]<=10000
            and type(a[6]) is int and 0<=a[6]<=2**32-1 and type(a[7]) is int and a[1]+3<=a[7]<=2000 and isinstance(a[8],list))
        if ok and a[8]:
            from datetime import datetime
            rows=a[8]
            ok=a[1]+3<=len(rows)<=500
            previous=None
            for row in rows:
                if not isinstance(row,list) or len(row)!=6 or not isinstance(row[0],str) or not all(number(x) for x in row[1:]):
                    ok=False
                    break
                try:
                    date=datetime.fromisoformat(row[0])
                    if date.tzinfo is not None or (previous is not None and date<=previous):
                        ok=False
                    previous=date
                except ValueError:
                    ok=False
                o,h,l,c,v=row[1:]
                if not (0<l<=min(o,c)<=max(o,c)<=h and v>=0):
                    ok=False
    if not ok:
        raise ValueError("Invalid or unsupported inputs for "+name)
    return a

def plan(name,image,values=None):
    r=RECIPES[name]
    smoke=values is None
    a=validate(name,r["fixture"] if smoke else values)
    payload=json.dumps(a,separators=(",",":"),allow_nan=False)
    if len(payload)>36000:
        raise ValueError("Serialized inputs exceed 36,000 characters")
    # Chunk only data, never executable text; join inside the sandbox.
    chunks=[payload[i:i+1800] for i in range(0,len(payload),1800)]
    # Separate prelude from body to remain within the manager argv limit.
    body=r["body"]+"\n"+(r["check"]+"\n" if smoke else "")+"print(json.dumps(result,indent=2,allow_nan=False,default=lambda x:x.item()))\n"
    # Keep the prefix separate from the body, both reviewed by the plan digest.
    launcher="import sys; pre=sys.argv.pop(1); body=sys.argv.pop(1); exec(compile(pre+body, \"<recipe>\", \"exec\"), globals())"
    return manager.validate_plan({"repo":r["repo"],"commit":PINS[r["repo"]],"image":image,
        "steps":[["python3","-c",launcher,PREFIX,body,r["entry"],*chunks]],"timeout":180})

def receipt(root,name,image):
    p=plan(name,image)
    return manager.safe_path(root,"packages",name,p["commit"],image[7:]+".json"),{
        "recipe":name,"repo":p["repo"],"commit":p["commit"],"image":image,
        "qualification_digest":manager.digest(p),"status":"qualified-quant-fixture"}

def install(root,name,image,approved):
    p=plan(name,image)
    if manager.digest(p)!=approved:
        raise ValueError("Approval does not match reviewed plan")
    dest,data=receipt(root,name,image)
    if dest.exists():
        if json.loads(dest.read_text())!=data:
            raise ValueError("Existing receipt differs; preserve and review")
        print("Already qualified:",dest)
        return 0
    rc=manager.run_plan(root,p,approved)
    if rc==0:
        manager.write_new(dest,data)
        print("Independent program qualified:",dest)
    return rc

def run(root,name,image,values):
    p=plan(name,image,values)
    dest,data=receipt(root,name,image)
    if not dest.is_file() or json.loads(dest.read_text())!=data:
        raise ValueError("Qualify exact source and runtime first")
    print("Offline research only; no live broker or trading instructions.",file=sys.stderr)
    return manager.run_plan(root,p,manager.digest(p))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=Path.home()/"core-ai-lab")
    sub=parser.add_subparsers(dest="action",required=True)
    sub.add_parser("list")
    for action in ("review","install","run"):
        q=sub.add_parser(action)
        q.add_argument("recipe",choices=RECIPES)
        q.add_argument("--image",required=True)
        if action=="install": q.add_argument("--approve",required=True)
        if action=="run":
            group=q.add_mutually_exclusive_group(required=True)
            group.add_argument("--params")
            group.add_argument("--params-file",type=Path)
    a=parser.parse_args()
    if a.action=="list":
        for name,r in RECIPES.items(): print(name,r["runtime"],r["fields"])
        return 0
    if a.action=="review":
        p=plan(a.recipe,a.image)
        print(json.dumps(p,indent=2))
        print("Approval digest:",manager.digest(p))
        return 0
    if a.action=="install": return install(a.root,a.recipe,a.image,a.approve)
    raw=a.params
    if a.params_file is not None:
        with a.params_file.open("rb") as f:
            raw=f.read(36001)
        if len(raw)>36000: raise ValueError("Input file exceeds 36,000 bytes")
    return run(a.root,a.recipe,a.image,json.loads(raw))

if __name__=="__main__":
    try:
        sys.exit(main())
    except (ValueError,OSError,subprocess.SubprocessError) as exc:
        print("STOP:",str(exc),file=sys.stderr)
        sys.exit(1)
