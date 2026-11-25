#!/usr/bin/env bash
set -euo pipefail
# A single, explicitly approved rollout of the gateway and normal workstation release.
[[ $# == 1 && "$1" == --approve-deploy ]] || { echo 'Review lab/INTEGRATION.md and run with --approve-deploy to authorize service start/restart and normal application deployment.' >&2; exit 1; }
[[ $EUID != 0 && $(id -un) == coreeye ]] || { echo 'Run as the existing coreeye lab owner.' >&2; exit 1; }
LAB="$HOME/core-ai-lab/manager"
APP="$HOME/core-ai"
cd "$LAB"
[[ $(pwd -P) == /home/coreeye/core-ai-lab/manager ]] || { echo 'Unexpected lab path.' >&2; exit 1; }
[[ $(git rev-parse HEAD) == $(git -C "$APP" rev-parse HEAD) ]] || { echo 'Both checkouts must be on the same reviewed release.' >&2; exit 1; }
[[ -z $(git status --porcelain --untracked-files=normal) && -z $(git -C "$APP" status --porcelain --untracked-files=normal) ]] || { echo 'Preserve local changes before deployment.' >&2; exit 1; }
python3 -m unittest discover -s tests -p 'test_independent*.py' -v
command -v prlimit >/dev/null
getent group core-ai >/dev/null
getent group docker >/dev/null
[[ -d "$HOME/core-ai-lab/reports" ]]
python3 lab/gateway.py --catalog | python3 -c 'import json,sys; d=json.load(sys.stdin); p=d["programs"]; print("Qualified",sum(x["state"]=="qualified-receipt" for x in p),"/",len(p)); sys.exit(not p or any(x["state"]!="qualified-receipt" for x in p))'
sudo systemd-analyze verify deploy/core-ai-lab-gateway.service
UNIT=/etc/systemd/system/core-ai-lab-gateway.service
if sudo test -e "$UNIT"; then
    sudo cmp deploy/core-ai-lab-gateway.service "$UNIT" || { echo 'Existing service definition differs. Review before replacing.' >&2; exit 1; }
else
    sudo install -m 0644 deploy/core-ai-lab-gateway.service "$UNIT"
fi
sudo systemctl daemon-reload
sudo systemctl enable core-ai-lab-gateway
sudo systemctl restart core-ai-lab-gateway
sudo systemctl is-active core-ai-lab-gateway
# Wait only for the known private socket, then execute the original qualified numeric fixture as the app user.
for i in $(seq 1 20); do
    [[ -S /run/core-ai-lab/gateway.sock ]] && break
    sleep 1
done
sudo -u core-ai python3 -c '
import json,socket
def call(body,timeout):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect("/run/core-ai-lab/gateway.sock")
        s.sendall(json.dumps(body).encode()+b"\n")
        with s.makefile("rb") as f: d=json.loads(f.readline())
    assert d["ok"],d
    return d["data"]
catalog=call({"action":"catalog"},45)
assert all(p["state"]=="qualified-receipt" for p in catalog["programs"])
result=call({"action":"run","recipe":"position-sizing","values":[10000,.01,100,95,0,0],"extension":None,"file_data":None},150)
assert result["state"]=="succeeded" and result["result"]["units"]==20,result
print("Gateway catalog and actual position-sizing execution PASS:",result["id"])
'
# Existing installer owns backup, schema migration, release and rollback.
cd "$APP"
bash scripts/install-workstation.sh
sudo systemctl is-active core-ai-api core-ai-worker core-ai-lab-gateway
echo 'Open CORE-AI > Tools, then enable program.list/program.run in Agents for Chat/Tasks.'
