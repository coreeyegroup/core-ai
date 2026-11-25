#!/usr/bin/env python3
"""Offline research and engineering programs from reviewed pinned repositories."""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys

import manager

PINS={
 "mvanhorn/last30days-skill":"7c2e1c2b099b13abd4397910168c4f53e638bb21",
 "egonex-ai/understand-anything":"b232f356446295e4eaa05b9b285e08ce5cd5e8a0",
 "cathrynlavery/diagram-design":"b228c5d77794a84150fca41b22940bb316b1398d",
 "ml4t/skills":"691857537a0c8befc11dc2f2ad7a458b7c7e801c",
}
GRAPH_FIXTURE=[
 {"nodes":[{"id":"file:a.py","type":"file","name":"a.py","filePath":"a.py","complexity":"low"}],"edges":[]},
 {"nodes":[{"id":"file:a.py","type":"file","name":"a.py","filePath":"a.py","complexity":"low"},{"id":"file:b.py","type":"file","name":"b.py","filePath":"b.py","complexity":"medium"}],
  "edges":[{"source":"file:a.py","target":"file:b.py","type":"imports","weight":1,"direction":"forward"},{"source":"file:a.py","target":"file:missing.py","type":"imports","weight":1,"direction":"forward"}]},
]
RECIPES={
 "research-mock":("mvanhorn/last30days-skill","skills/last30days/scripts/last30days.py",["test topic"],
 """import subprocess
out=subprocess.check_output([sys.executable,entry,a[0],'--mock','--emit=json','--no-browser-cookies','--no-research-persistence'],text=True)
d=json.loads(out)
if d.get('schema_version')!='1.4' or d.get('query')!=a[0] or not all(k in d for k in ('results','clusters','source_status')):
    raise SystemExit('Unexpected mock report schema')
result={'provenance':'mock-fixtures-not-live-research','report':d}""",
 "assert result['report']['query']=='test topic'"),
 "knowledge-graph-merge":("egonex-ai/understand-anything","understand-anything-plugin/skills/understand/merge-batch-graphs.py",GRAPH_FIXTURE,
 """m=load()
graph,report=m.merge_and_normalize(a)
ids={n['id'] for n in graph['nodes']}
if len(ids)!=len(graph['nodes']) or any(e['source'] not in ids or e['target'] not in ids for e in graph['edges']):
    raise SystemExit('Graph contains duplicate nodes or dangling edges')
result={'graph':graph,'review_report':report}""",
 "assert len(graph['nodes'])==2 and len(graph['edges'])==1;assert {n['complexity'] for n in graph['nodes']}=={'simple','moderate'}"),
 "diagram-prism":("cathrynlavery/diagram-design","scripts/axonometry.py",[80,40,30,5],
 """m=load()
w,d,h,r=a
p=m.Proj(0,0)
shape=m.prism(p,m.Rect(0,0,w,d,r),0,h)
result={'projection':'2:1 dimetric','geometry':shape,'origin':p.iso(0,0,0),'top_corner':p.iso(w,d,h)}""",
 "assert result['origin']==(0,0);assert result['top_corner']==(40,30);assert all(shape[k].startswith('M') for k in ('top','left','right','sil'))"),
 "ml4t-chapter-map":("ml4t/skills","scripts/generate_chapter_map.py",[],
 """import subprocess
out=subprocess.check_output([sys.executable,entry,'--print'],text=True)
if '# Skill Chapter Map' not in out or '## By chapter' not in out or '## By skill' not in out:
    raise SystemExit('Unexpected ML4T chapter map')
result={'markdown':out}""",
 "assert '## By chapter' in result['markdown']"),
}
PREFIX="""import sys,json,importlib.util
entry=sys.argv[1]
a=json.loads(''.join(sys.argv[2:]))
def load():
    spec=importlib.util.spec_from_file_location('core_lab_research_upstream',entry)
    mod=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=mod
    spec.loader.exec_module(mod)
    return mod
"""
LAUNCHER="import sys; pre=sys.argv.pop(1); body=sys.argv.pop(1); exec(compile(pre+body, '<recipe>', 'exec'), globals())"

def validate(name,a):
    if not isinstance(a,list):
        raise ValueError("Use a JSON array")
    if name=="research-mock":
        ok=(len(a)==1 and isinstance(a[0],str) and 1<=len(a[0].strip())<=200 and
            not a[0].startswith("-") and all(ord(c)>=32 for c in a[0]))
    elif name=="knowledge-graph-merge":
        ok=1<=len(a)<=30
        total=0
        for b in a:
            if not isinstance(b,dict) or set(b)!={"nodes","edges"} or not all(isinstance(b[k],list) for k in ("nodes","edges")):
                ok=False
                break
            total+=len(b["nodes"])+len(b["edges"])
            for n in b["nodes"]:
                if not isinstance(n,dict) or not all(isinstance(n.get(k),str) and n[k] for k in ("id","type","name")):
                    ok=False
            for e in b["edges"]:
                if not isinstance(e,dict) or not all(isinstance(e.get(k),str) and e[k] for k in ("source","target","type")):
                    ok=False
        ok=ok and 1<=total<=500
    elif name=="diagram-prism":
        ok=(len(a)==4 and all(type(v) in (int,float) and math.isfinite(v) and 0<=v<=10000 for v in a)
            and min(a[:3])>0 and a[3]<=min(a[:2])/2)
    else:
        ok=a==[]
    if not ok: raise ValueError("Invalid inputs for "+name)
    return a

def plan(name,image,values=None):
    repo,entry,fixture,body,check=RECIPES[name]
    a=validate(name,fixture if values is None else values)
    payload=json.dumps(a,separators=(",",":"),allow_nan=False)
    if len(payload)>36000: raise ValueError("Input exceeds 36,000 serialized characters")
    chunks=[payload[i:i+1800] for i in range(0,len(payload),1800)]
    body=body+"\n"+(check+"\n" if values is None else "")+"print(json.dumps(result,indent=2,allow_nan=False))\n"
    return manager.validate_plan({"repo":repo,"commit":PINS[repo],"image":image,
        "steps":[["python3","-c",LAUNCHER,PREFIX,body,entry,*chunks]],"timeout":180})

def receipt(root,name,image):
    p=plan(name,image)
    return manager.safe_path(root,"packages",name,p["commit"],image[7:]+".json"),{
        "recipe":name,"repo":p["repo"],"commit":p["commit"],"image":image,
        "qualification_digest":manager.digest(p),"status":"qualified-offline-fixture"}

def install(root,name,image,approved):
    p=plan(name,image)
    if manager.digest(p)!=approved: raise ValueError("Approval does not match reviewed plan")
    dest,data=receipt(root,name,image)
    if dest.exists():
        if json.loads(dest.read_text())!=data: raise ValueError("Existing receipt differs; preserve and review")
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
    if not dest.is_file() or json.loads(dest.read_text())!=data: raise ValueError("Qualify exact source and runtime first")
    return manager.run_plan(root,p,manager.digest(p))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root",type=Path,default=Path.home()/"core-ai-lab")
    sub=parser.add_subparsers(dest="action",required=True)
    sub.add_parser("list")
    for action in ("review","install","run"):
        p=sub.add_parser(action)
        p.add_argument("recipe",choices=RECIPES)
        p.add_argument("--image",required=True)
        if action=="install": p.add_argument("--approve",required=True)
        if action=="run":
            g=p.add_mutually_exclusive_group(required=True)
            g.add_argument("--params")
            g.add_argument("--params-file",type=Path)
    a=parser.parse_args()
    if a.action=="list":
        for name,r in RECIPES.items(): print(name,r[0],r[1])
        return 0
    if a.action=="review":
        p=plan(a.recipe,a.image)
        print(json.dumps(p,indent=2))
        print("Approval digest:",manager.digest(p))
        return 0
    if a.action=="install": return install(a.root,a.recipe,a.image,a.approve)
    raw=a.params
    if a.params_file is not None:
        with a.params_file.open("rb") as f: raw=f.read(36001)
        if len(raw)>36000: raise ValueError("Input file exceeds 36,000 bytes")
    return run(a.root,a.recipe,a.image,json.loads(raw))

if __name__=="__main__":
    try:
        sys.exit(main())
    except (ValueError,OSError,subprocess.SubprocessError) as exc:
        print("STOP:",str(exc),file=sys.stderr)
        sys.exit(1)
