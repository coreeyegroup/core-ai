#!/usr/bin/env bash
# Isolated project runtimes. Existing services and system Python/Node are preserved.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ $EUID == 0 ]]; then echo 'Run as your normal Ubuntu user; sudo is requested where required.' >&2; exit 1; fi
. /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 22.04 || "$ID" == ubuntu && "$VERSION_ID" == 24.04 ]] || { echo 'Ubuntu 22.04 or 24.04 is required.' >&2; exit 1; }
[[ $(uname -m) == x86_64 ]] || { echo 'This release supports Ubuntu x86_64.' >&2; exit 1; }
sudo -v
TASK_MISSING=0
for TASK_COMMAND in curl git gpg xz wg; do
  command -v "$TASK_COMMAND" >/dev/null || TASK_MISSING=1
done
command -v caddy >/dev/null || TASK_MISSING=1
[[ -x /usr/lib/postgresql/18/bin/postgres ]] || TASK_MISSING=1
if [[ $TASK_MISSING == 1 ]]; then
  sudo apt-get update
  sudo apt-get install -y ca-certificates curl git gnupg xz-utils wireguard-tools
fi
if ! command -v caddy >/dev/null; then
  curl --fail --silent --show-error --location https://dl.cloudsmith.io/public/caddy/stable/gpg.key | sudo gpg --dearmor --yes -o /usr/share/keyrings/core-ai-caddy.gpg
  printf '%s\n' 'deb [signed-by=/usr/share/keyrings/core-ai-caddy.gpg] https://dl.cloudsmith.io/public/caddy/stable/deb/debian any-version main' | sudo tee /etc/apt/sources.list.d/core-ai-caddy.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y caddy
fi
if [[ ! -x /usr/lib/postgresql/18/bin/postgres ]]; then
  if ! apt-cache show postgresql-18 >/dev/null 2>&1; then
    curl --fail --silent --show-error --location https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo gpg --dearmor --yes -o /usr/share/keyrings/core-ai-postgresql.gpg
    printf 'deb [signed-by=/usr/share/keyrings/core-ai-postgresql.gpg] https://apt.postgresql.org/pub/repos/apt %s-pgdg main\n' "$VERSION_CODENAME" | sudo tee /etc/apt/sources.list.d/core-ai-postgresql.list >/dev/null
    sudo apt-get update
  fi
  sudo apt-get install -y postgresql-18 postgresql-client-18
fi
TASK_NODE=/opt/core-ai/toolchain/node-v26.13.0
if [[ ! -x "$TASK_NODE/bin/node" ]]; then
  [[ ! -e "$TASK_NODE" ]] || { echo 'Incomplete Node toolchain; inspect it before retrying.' >&2; exit 1; }
  TASK_BUILD=$(mktemp -d /tmp/core-ai-node.XXXXXXXX)
  curl --fail --show-error --location --retry 3 --proto '=https' --tlsv1.2 -o "$TASK_BUILD/node.tar.xz" https://nodejs.org/dist/v26.13.0/node-v26.13.0-linux-x64.tar.xz
  (cd "$TASK_BUILD" && printf '%s\n' 'd28a96af6c38596f6d9d97c0ee531c13d238d757742387d1928de822d959e997  node.tar.xz' | sha256sum --check -)
  tar -xJf "$TASK_BUILD/node.tar.xz" -C "$TASK_BUILD"
  sudo install -d -m 0755 /opt/core-ai/toolchain
  sudo mv "$TASK_BUILD/node-v26.13.0-linux-x64" "$TASK_NODE"
  sudo chown -R root:root "$TASK_NODE"
fi
[[ $("$TASK_NODE/bin/node" --version) == v26.13.0 ]] || { echo 'Unexpected Node runtime.' >&2; exit 1; }
bash scripts/repair-python.sh
sudo systemctl enable --now caddy
printf '%s\n' 'Infrastructure ready: isolated Node 26.13.0 / Python 3.14.10, PostgreSQL 18, Caddy, WireGuard.' 'Existing application services and package versions were preserved.'
