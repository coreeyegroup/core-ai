#!/usr/bin/env python3
"""Additional reviewed, pinned standalone programs; offline analysis only."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

import manager

MARIAN = "marian2js/trading-skills"
REDDY = "reddygopalkrishna/trading-skills"
OPENAI = "openai/skills"
MATH = "skills/_lib/calculations.py"
METRICS = "core/tradekit/metrics.py"
OPTIONS = "core/tradekit/options.py"
NOTEBOOK = "skills/.curated/jupyter-notebook/scripts/new_notebook.py"
PINS = {
    MARIAN: "f1ae7d481154b49192681187cb08d39d7e2d4524",
    REDDY: "df92aab5437202810a8fc1a7b666d35c539e0b63",
    OPENAI: "49f948faa9258a0c61caceaf225e179651397431",
}
RECIPES = {
    "contract-sizing": (MARIAN, MATH,
        "equity,risk_fraction,entry,stop,slippage_per_unit,fee_per_unit,multiplier,round_lot",
        [100000, .01, 100, 95, 0, 0, 25, 1],
        "result=m['fixed_fractional_position_size'](account_equity=a[0],risk_fraction=a[1],entry_price=a[2],stop_price=a[3],slippage_per_unit=a[4],fee_per_unit=a[5],contract_multiplier=a[6],round_lot=a[7])",
        "close(result['size'],8);close(result['unit_risk'],125);close(result['total_risk'],1000)"),
    "trade-expectancy": (MARIAN, MATH, "win_rate,average_win,average_loss",
        [.6, 2, 1],
        "result=m['expectancy'](win_rate=a[0],average_win=a[1],average_loss=a[2])",
        "close(result['expectancy'],.8);close(result['expectancy_r'],.8)"),
    "trade-statistics": (MARIAN, MATH, "sequence of trade PnL values",
        [100,-50,150,-100],
        "result=m['trade_statistics'](a);result={k:(v if math.isfinite(v) else None) for k,v in result.items()}",
        "close(result['net_result'],100);close(result['profit_factor'],250/150);close(result['max_drawdown'],100)"),
    "equity-drawdown": (REDDY, METRICS, "sequence of positive equity values",
        [100,120,90,110,130],
        "result=m['max_drawdown'](a)",
        "close(result['max_drawdown_pct'],-25)"),
    "option-greeks": (REDDY, OPTIONS, "spot,strike,years,annual_rate,annual_volatility,dividend_yield",
        [100,100,1,.05,.2,0],
        "result={'call':m['greeks'](*a[:5],'call',a[5]),'put':m['greeks'](*a[:5],'put',a[5])}",
        "close(result['call']['price'],10.450583572);close(result['put']['price'],5.573526022);close(result['call']['delta']-result['put']['delta'],1)"),
    "option-implied-vol": (REDDY, OPTIONS, "premium,spot,strike,years,annual_rate,kind,dividend_yield",
        [10.450583572,100,100,1,.05,"call",0],
        "result={'implied_volatility':m['implied_vol'](*a)}",
        "close(result['implied_volatility'],.2)"),
    "notebook-scaffold": (OPENAI, NOTEBOOK, "kind (experiment/tutorial),title",
        ["experiment","CoreEye qualification"],
        """import subprocess
from pathlib import Path
out=Path('/tmp/result.ipynb')
subprocess.run([sys.executable,sys.argv[1],'--kind',a[0],'--title='+a[1],'--out',str(out)],check=True,stdout=sys.stderr)
result=json.loads(out.read_text())
title=result['cells'][0]['source']
if not isinstance(result.get('nbformat'),int) or not title[0].startswith('# '+a[0].title()+': '+a[1]):
    raise SystemExit('Unexpected notebook structure')""",
        "assert result['cells'][0]['cell_type']=='markdown'"),
}

PREFIX = """import json, math, runpy, sys
a=json.loads(sys.argv[2])
m=runpy.run_path(sys.argv[1])
def close(actual,expected):
    if not math.isclose(actual,expected,rel_tol=1e-6,abs_tol=1e-7):
        raise SystemExit('Unexpected fixture result: %r != %r'%(actual,expected))
"""

def numeric(x):
    return type(x) in (int,float) and abs(x) <= 1e12 and math.isfinite(x)

def validate(name,a):
    if not isinstance(a,list):
        raise ValueError("Use a JSON array")
    if name == "notebook-scaffold":
        if len(a)!=2 or a[0] not in ("experiment","tutorial") or not isinstance(a[1],str) or not 1<=len(a[1].strip())<=200 or any(ord(c)<32 for c in a[1]):
            raise ValueError("Expected notebook kind and single-line title")
        return a
    if name in ("trade-statistics","equity-drawdown"):
        if not 1<=len(a)<=100 or not all(numeric(v) for v in a):
            raise ValueError("Expected 1-100 finite values")
        if name=="equity-drawdown" and any(v<=0 for v in a):
            raise ValueError("Equity must be positive")
        return a
    n=len(RECIPES[name][3])
    if len(a)!=n or not all(numeric(v) for i,v in enumerate(a) if not(name=="option-implied-vol" and i==5)):
        raise ValueError("Invalid numeric inputs")
    if name=="contract-sizing":
        ok=a[0]>0 and 0<a[1]<=1 and a[2]>0 and a[3]>0 and a[2]!=a[3] and a[4]>=0 and a[5]>=0 and a[6]>0 and a[7]>0
    elif name=="trade-expectancy":
        ok=0<=a[0]<=1 and a[1]>=0 and a[2]>0
    elif name=="option-greeks":
        ok=a[0]>0 and a[1]>0 and 0<a[2]<=100 and -1<=a[3]<=1 and 0<a[4]<=5 and -1<=a[5]<=1
    else:
        ok=a[0]>0 and a[1]>0 and a[2]>0 and 0<a[3]<=100 and -1<=a[4]<=1 and a[5] in ("call","put") and -1<=a[6]<=1
    if not ok:
        raise ValueError("Unsupported inputs")
    return a

def plan(name,image,values=None):
    repo,entry,fields,fixture,body,check=RECIPES[name]
    smoke=values is None
    a=validate(name,fixture if smoke else values)
    code=PREFIX+body+"\n"+(check+"\n" if smoke else "")+"print(json.dumps(result,indent=2,allow_nan=False))\n"
    return manager.validate_plan({"repo":repo,"commit":PINS[repo],"image":image,
        "steps":[["python3","-c",code,entry,json.dumps(a,allow_nan=False)]],"timeout":120})

def receipt(root,name,image):
    p=plan(name,image)
    data={"recipe":name,"repo":p["repo"],"commit":p["commit"],"image":image,
          "qualification_digest":manager.digest(p),"status":"qualified-fixture"}
    return manager.safe_path(root,"packages",name,p["commit"],image[7:]+".json"),data

def install(root,name,image,approved):
    p=plan(name,image)
    if manager.digest(p)!=approved:
        raise ValueError("Approval does not match exact plan")
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

def _limit():
    import resource
    resource.setrlimit(resource.RLIMIT_FSIZE,(2*1024*1024,2*1024*1024))

def run(root,name,image,values,output=None):
    p=plan(name,image,values)
    dest,data=receipt(root,name,image)
    if not dest.is_file() or json.loads(dest.read_text())!=data:
        raise ValueError("Qualify this exact program and runtime first")
    if name!="notebook-scaffold":
        if output is not None:
            raise ValueError("--output is for notebook-scaffold only")
        return manager.run_plan(root,p,manager.digest(p))
    if output is None or output.suffix!=".ipynb" or output.exists() or output.is_symlink():
        raise ValueError("Supply a new .ipynb output path; no overwrite")
    path=manager.source(root,p["repo"],p["commit"])
    manager.verify(path,p["commit"])
    container="core-ai-lab-notebook-"+uuid.uuid4().hex
    state={"repo":p["repo"],"commit":p["commit"],"recipe":name,"image":image,"state":"failed"}
    try:
        with tempfile.TemporaryFile() as stream:
            rc=subprocess.run(manager.docker_args(path,p,container),stdout=stream,
                preexec_fn=_limit,timeout=p["timeout"],check=False).returncode
            if rc!=0:
                return 1
            stream.seek(0)
            notebook=json.load(stream)
            if not isinstance(notebook,dict) or not isinstance(notebook.get("cells"),list) or not isinstance(notebook.get("nbformat"),int):
                raise ValueError("Invalid notebook output")
            # exclusive creation, no force/overwrite or notebook execution
            with output.open("x",encoding="utf-8") as f:
                json.dump(notebook,f,indent=2,ensure_ascii=False)
                f.write("\n")
        state["state"]="created"
        print("Created:",output)
        return 0
    except subprocess.TimeoutExpired:
        state["state"]="timeout"
        subprocess.run(["docker","kill",container],timeout=20,check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        return 1
    finally:
        print("Execution record:",manager.report(root,p["repo"],state),file=sys.stderr)

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
            q.add_argument("--params",required=True)
            q.add_argument("--output",type=Path)
    a=parser.parse_args()
    if a.action=="list":
        for name,item in RECIPES.items(): print(name,item[2],json.dumps(item[3]))
        return 0
    if a.action=="review":
        p=plan(a.recipe,a.image)
        print(json.dumps(p,indent=2))
        print("Approval digest:",manager.digest(p))
        return 0
    if a.action=="install": return install(a.root,a.recipe,a.image,a.approve)
    return run(a.root,a.recipe,a.image,json.loads(a.params),a.output)

if __name__=="__main__":
    try:
        sys.exit(main())
    except (ValueError,OSError,subprocess.SubprocessError) as exc:
        print("STOP:",str(exc),file=sys.stderr)
        sys.exit(1)
