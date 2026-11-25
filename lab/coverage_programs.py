#!/usr/bin/env python3
"""Original upstream offline programs and isolated component tests for uncovered repositories."""
import json
import math
import sys
import subprocess
from pathlib import Path
import manager

PYTHON="python:3.12-slim"
NODE="core-ai-lab-opencode:0.1.0"
OFFICE="core-ai-lab-office:0.1.0"
QUANT="core-ai-lab-quant:0.1.0"
# Explicit pins; changes require review and a new receipt.
PINS={
 "addyosmani/agent-skills":"e997ac5b9a74eab332d5e9793bb38a38c8cfdd74",
 "anthropics/financial-services":"3e32c2287dcb637c184c01cc0ad82d6af7e9bb0f",
 "ayghri/i-have-adhd":"1ecea1993b7fce257ffbd686c070948b5e07eda6",
 "blader/humanizer":"a32f24407364c74c812b43c15926d638bee1e072",
 "composiohq/awesome-claude-skills":"be2a406907dbc61b73e6827ded415c96139d13a2",
 "dietrichgebert/ponytail":"ebd8654c2c627f721eb8f9c0d1bd4090a29f9e10",
 "gauss314/skills":"5156f818420dc9098ac1071e26d34bb7294efe12",
 "juliusbrussee/caveman":"47c61be2d10a354f0c5cbe2b90959d24c06b16c6",
 "mattpocock/skills":"d65391149dbb5fe76478e76fa8d5122b2aa5a70e",
 "obra/superpowers":"22f0b463e7a5e579904dd6211a520321035526f7",
 "vercel-labs/agent-skills":"5a37a6329fbad3666c3207392a6a7c0110e92efb",
 "wshobson/agents":"c96b5f6552dba32e4492307493ee613581430715",
}
def diagnostic(repo,runtime,commands,scope):
    return dict(repo=repo,runtime=runtime,fixture=[],fields="No arguments",mode="diagnostic",commands=commands,scope=scope)

def calculation(repo,runtime,entry,fields,fixture,body,check,scope):
    return dict(repo=repo,runtime=runtime,entry=entry,fields=fields,fixture=fixture,body=body,check=check,mode="offline",scope=scope)

RECIPES={
 "addy-skill-lint":diagnostic("addyosmani/agent-skills",NODE,[["node","scripts/validate-skills.js"]],"Upstream skill and persona validator, not agent execution."),
 "humanizer-package-check":diagnostic("blader/humanizer",PYTHON,[["python3","scripts/validate-package.py"]],"Package consistency only; no rewriting-model qualification."),
 "matt-plugin-version-check":diagnostic("mattpocock/skills",NODE,[["node","scripts/sync-plugin-version.mjs","--check"]],"Upstream version-consistency check; YAML parser and host integrations remain pending."),
 "ponytail-plugin-check":diagnostic("dietrichgebert/ponytail",NODE,[["node","--test","tests/opencode-plugin.test.js"]],"Upstream V1/V2 hook and registration fixtures; no live host or model."),
 "caveman-directive-check":diagnostic("juliusbrussee/caveman",NODE,[["node","--test","extension/test/directive.test.mjs"]],"Actual extension directive logic tests; no browser extension or CLI binary installation."),
 "superpowers-plugin-check":diagnostic("obra/superpowers",NODE,[
     ["node","tests/opencode/test-hook-registration.mjs",".opencode/plugins/superpowers.js"],
     ["node","tests/opencode/test-skill-registration.mjs",".opencode/plugins/superpowers.js"]],"Upstream hook and skill registration fixtures; separate real OpenCode probe required."),
 "adhd-plugin-check":diagnostic("ayghri/i-have-adhd",NODE,[["node","--input-type=module","-e",
     "import assert from 'node:assert/strict';import {execFileSync} from 'node:child_process';import {resolve} from 'node:path';import {mkdirSync,writeFileSync} from 'node:fs';const env={...process.env,XDG_CONFIG_HOME:'/tmp/adhd-fixture'};const run=mode=>execFileSync(process.execPath,['tests/opencode_plugin_driver.mjs',resolve('.opencode/plugins/i-have-adhd.mjs'),mode],{encoding:'utf8',env});assert.equal(run('context'),'');assert.equal(JSON.parse(run('skill'))[0].id,'i-have-adhd');assert.equal(JSON.parse(run('command'))[0].name,'i-have-adhd');mkdirSync('/tmp/adhd-fixture/opencode',{recursive:true});writeFileSync('/tmp/adhd-fixture/opencode/.i-have-adhd-always','');assert.match(run('context'),/ADHD MODE ACTIVE/);console.log(JSON.stringify({registered:true,opt_in_gate:true}));"]],"Actual upstream driver verifies registration and opt-in gate, not live host."),
 "agent-name-collision-scan":diagnostic("wshobson/agents",PYTHON,[["python3","tools/check_agent_name_collisions.py","--root","."]],"Original collision report; duplicates are findings, not successful native installation."),
 "dcf-assumption-check":calculation("anthropics/financial-services",OFFICE,"plugins/vertical-plugins/financial-analysis/skills/dcf-model/scripts/validate_dcf.py",
     ["terminal_growth","wacc"],[.03,.08],
     "import openpyxl\nw=openpyxl.Workbook();s=w.active;s.title='DCF';w.create_sheet('WACC');w.create_sheet('Sensitivity');s.append(['Terminal Growth',a[0]]);s.append(['WACC',a[1]]);s.append(['PV Terminal Value',60]);s.append(['Enterprise Value',100]);w.save('/tmp/assumptions.xlsx');result=m['DCFModelValidator']('/tmp/assumptions.xlsx').validate_all();result['scope']='synthetic assumptions workbook, not a valuation or full DCF audit'",
     "assert result['status']=='PASS';s['B1']=.10;w.save('/tmp/invalid.xlsx');bad=m['DCFModelValidator']('/tmp/invalid.xlsx').validate_all();assert bad['status']=='FAIL' and any('CRITICAL' in e for e in bad['errors'])",
     "Synthetic workbook only; upstream WACC range helper can emit a warning because Workbook.get is unsupported. Not a full model validator."),
 "animation-easing":calculation("composiohq/awesome-claude-skills",PYTHON,"slack-gif-creator/core/easing.py",
     ["start","end","progress","easing"],[0,100,.5,"ease_in"],
     "result={'interpolated':m['interpolate'](*a),'easing':a[3]}",
     "assert result['interpolated']==25",
     "Original interpolation utility; GIF rendering and external app connectors not installed."),
 "gauss-indicators":calculation("gauss314/skills",QUANT,"skills/backtesting/scripts/indicators.py",
     ["closing_prices","window"],[[1,2,3,4,5],3],
     "import math\nclean=lambda xs:[float(x) if math.isfinite(x) else None for x in xs]\nresult={'sma':clean(m['sma'](*a)),'ema':clean(m['ema'](*a)),'wma':clean(m['wma'](*a))}",
     "assert result['sma']==[None,None,2,3,4];assert result['ema'][0]==1 and abs(result['ema'][-1]-4.0625)<1e-8;assert abs(result['wma'][-1]-26/6)<1e-8",
     "Offline moving averages on provided data; no FRED, Alpaca or broker access."),
 "vercel-rate-limit-check":dict(repo="vercel-labs/agent-skills",runtime=NODE,fixture=["Run 50 parallel Notion requests."],
     fields=["recommendation"],mode="offline",scope="Upstream static heuristic, not current provider-limit evidence or a live Vercel audit."),
}
EASING={"linear","ease_in","ease_out","ease_in_out","bounce_in","bounce_out","bounce","elastic_in","elastic_out","elastic","back_in","back_out","back_in_out","anticipate","overshoot"}
def number(x):
    return type(x) in (int,float) and math.isfinite(x) and abs(x)<=1e12

def validate(name,a):
    if not isinstance(a,list):raise ValueError("Expected JSON array")
    if name=="dcf-assumption-check":
        ok=len(a)==2 and all(number(x) and 0<x<1 for x in a)
    elif name=="animation-easing":
        ok=len(a)==4 and all(number(x) for x in a[:3]) and 0<=a[2]<=1 and isinstance(a[3],str) and a[3] in EASING
    elif name=="gauss-indicators":
        ok=len(a)==2 and isinstance(a[0],list) and 2<=len(a[0])<=500 and all(number(x) for x in a[0]) and type(a[1]) is int and 1<=a[1]<=len(a[0])
    elif name=="vercel-rate-limit-check":
        ok=len(a)==1 and isinstance(a[0],str) and 1<=len(a[0])<=1000 and all(ord(c)>=32 for c in a[0])
    else:ok=a==[]
    if not ok:raise ValueError("Invalid inputs for "+name)
    return a

def plan(name,image,values=None):
    r=RECIPES[name]
    a=validate(name,r["fixture"] if values is None else values)
    if "commands" in r:
        steps=r["commands"]
    elif name=="vercel-rate-limit-check":
        body="import assert from 'node:assert/strict';import {apply} from './skills/vercel-optimize/lib/sanitizers/rate-limit.mjs';const rec={fix:JSON.parse(process.argv[1])[0]};const result=apply(rec);"
        if values is None:body+="assert.equal(result.needsReview,true);assert.ok(result.tags.some(t=>t.startsWith('rate-limit:Notion:50/3')));"
        body+="console.log(JSON.stringify({recommendation:rec.fix,findings:result,scope:'static upstream heuristic; verify current provider limits'}));"
        steps=[["node","--input-type=module","-e",body,json.dumps(a)]]
    else:
        payload=json.dumps(a,separators=(",",":"),allow_nan=False)
        if len(payload)>36000:raise ValueError("Input too large")
        prefix="import json,sys,runpy\nm=runpy.run_path(sys.argv[1]);a=json.loads(''.join(sys.argv[2:]))\n"
        body=prefix+r["body"]+"\n"+(r["check"]+"\n" if values is None else "")+"print(json.dumps(result,allow_nan=False))"
        steps=[["python3","-c",body,r["entry"],*[payload[i:i+1800] for i in range(0,len(payload),1800)]]]
    # Existing native image has XDG defaults for its normal user; use the
    # ephemeral writable HOME of the lab container for Node diagnostics.
    if r["runtime"]==NODE:
        steps=[["env","XDG_CONFIG_HOME=/tmp/home/.config","XDG_DATA_HOME=/tmp/home/.local/share","XDG_CACHE_HOME=/tmp/home/.cache",*s] for s in steps]
    return manager.validate_plan({"repo":r["repo"],"commit":PINS[r["repo"]],"image":image,"steps":steps,"timeout":180})

def receipt(root,name,image):
    p=plan(name,image)
    return manager.safe_path(root,"packages",name,p["commit"],image[7:]+".json"),{
        "recipe":name,"repo":p["repo"],"commit":p["commit"],"image":image,
        "qualification_digest":manager.digest(p),"status":"qualified-offline-component"}

def install(root,name,image,approved):
    p=plan(name,image)
    if approved!=manager.digest(p):raise ValueError("Approval does not match reviewed plan")
    dest,data=receipt(root,name,image)
    if dest.exists():
        if json.loads(dest.read_text())!=data:raise ValueError("Existing receipt differs")
        return 0
    rc=manager.run_plan(root,p,approved)
    if rc==0:manager.write_new(dest,data)
    return rc
