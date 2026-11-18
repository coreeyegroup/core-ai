"""Stable Git-managed entry point; no third-party dashboard runtime."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import datetime

ROOT=Path(__file__).resolve().parents[1]

def run(*args,**kwargs):
    return subprocess.run(args,check=True,**kwargs)

def legacy_backup():
    """One consistent archive of superseded dashboard data before the first rebuild."""
    members=[str(p.relative_to(ROOT)) for p in (ROOT/'.env',ROOT/'config.env',ROOT/'runtime',ROOT/'data',ROOT/'data-anythingllm') if p.exists()]
    if not members:
        return
    marker=ROOT/'backups'/'legacy-dashboard-archived'
    if subprocess.run(['sudo','test','-f',str(marker)]).returncode==0:
        return
    running=[]
    if shutil.which('docker'):
        for name in ('core-ai-app-1','core-ai-webui-1'):
            r=subprocess.run(['sudo','docker','inspect','--format','{{index .Config.Labels "com.docker.compose.project"}} {{.State.Running}}',name],capture_output=True,text=True)
            if r.returncode==0 and r.stdout.strip()=='core-ai true':
                running.append(name)
    destination=ROOT/'backups'
    run('sudo','install','-d','-o','root','-g','root','-m','0700',str(destination))
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target=destination/('legacy-dashboard-'+stamp+'.tar.gz')
    try:
        if running:
            run('sudo','docker','stop',*running,stdout=subprocess.DEVNULL)
        run('sudo','tar','-czf',str(target),'-C',str(ROOT),*members)
        run('sudo','chmod','0600',str(target))
        run('sudo','touch',str(marker))
        print('Consistent private legacy archive:',target)
    finally:
        if running:
            run('sudo','docker','start',*running,stdout=subprocess.DEVNULL)

def main():
    parser=argparse.ArgumentParser(description='CORE-AI independent workstation')
    parser.add_argument('command',nargs='?',default='help',choices=['help','doctor','status','test-model','logs','publish','backup','legacy-backup','peer-add','set-login'])
    parser.add_argument('--public-key')
    parser.add_argument('--username')
    args=parser.parse_args()
    if args.command=='help':
        print('CORE-AI: ./core-ai install [--domain HOST] [--model-host PRIVATE_IP] [--endpoint VPS_HOST]')
        print('         ./core-ai update | doctor | test-model | logs | publish | backup')
        print('         ./core-ai set-login --username USER (prompts privately for the new password)')
        print('         ./core-ai peer-add --public-key KEY (called by the Windows installer)')
        return
    if args.command=='legacy-backup':
        legacy_backup()
    elif args.command=='set-login':
        if not args.username:
            raise ValueError('Supply --username with the desired administrator username.')
        run('sudo','python3',str(ROOT/'scripts/deploy-workstation.py'),'admin','set-login',str(ROOT),args.username)
    elif args.command=='logs':
        run('sudo','journalctl','-u','core-ai-api','-u','core-ai-worker','-n','120','--no-pager')
    elif args.command=='peer-add':
        if not args.public_key:
            raise ValueError('A laptop WireGuard public key is required.')
        import network
        network.validate_key(args.public_key)
        run('sudo','python3',str(ROOT/'scripts/deploy-workstation.py'),'admin','peer-add',str(ROOT),args.public_key)
    else:
        action='doctor' if args.command=='status' else args.command
        run('sudo','python3',str(ROOT/'scripts/deploy-workstation.py'),'admin',action,str(ROOT))
        if action=='doctor':
            import network
            network.doctor()

if __name__=='__main__':
    try:
        main()
    except (ValueError,subprocess.CalledProcessError) as exc:
        sys.exit('STOP: '+str(exc))
