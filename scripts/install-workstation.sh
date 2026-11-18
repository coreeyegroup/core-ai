#!/usr/bin/env bash
set -euo pipefail
umask 022
cd "$(dirname "$0")/.."
[[ $EUID != 0 ]] || { echo 'Run as your normal Ubuntu user.' >&2; exit 1; }
# Snapshot the old running application before any infrastructure or source-runtime change.
python3 scripts/manage.py legacy-backup
bash scripts/install-infra.sh
TASK_NODE=/opt/core-ai/toolchain/node-v26.13.0/bin
TASK_PYTHON=/opt/core-ai/toolchain/python-3.14.10/bin/python3.14
export PATH="$TASK_NODE:$PATH"
TASK_STAMP=$(date -u +%Y%m%dT%H%M%S)-$$
TASK_RELEASE=/opt/core-ai/releases/$TASK_STAMP
sudo install -d -m 0755 /opt/core-ai/releases
sudo install -d -o "$(id -u)" -g "$(id -g)" -m 0755 "$TASK_RELEASE"
cp -a backend "$TASK_RELEASE/backend"
# Build before touching the active release or routing.
"$TASK_PYTHON" -m venv "$TASK_RELEASE/.venv"
"$TASK_RELEASE/.venv/bin/python" -m pip install "$TASK_RELEASE/backend"
npm ci --prefix ui
npm run build --prefix ui
cp -a ui/dist "$TASK_RELEASE/ui"
git rev-parse HEAD > "$TASK_RELEASE/source-commit"
sudo python3 scripts/deploy-workstation.py "$TASK_RELEASE" "$(pwd)" "$@"
