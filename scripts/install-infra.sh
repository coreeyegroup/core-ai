#!/usr/bin/env bash
# Install missing prerequisites. Upgrade shared infrastructure only explicitly.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
[ "$(id -u)" -ne 0 ] || { printf 'Run as your normal deployment user; sudo is requested where needed.\n' >&2; exit 2; }
. /etc/os-release
[ "$ID" = ubuntu ] || { printf 'This installer supports Ubuntu only.\n' >&2; exit 2; }
sudo -v
if [ "${1:-install}" = infra-update ]; then
  packages=()
  for package in docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin caddy wireguard-tools; do
    if [ "$(dpkg-query -W -f='${db:Status-Status}' "$package" 2>/dev/null || true)" = installed ]; then
      packages+=("$package")
    fi
  done
  [ "${#packages[@]}" -gt 0 ] || { printf 'No managed infrastructure packages found.\n'; exit 2; }
  sudo apt-get update
  sudo apt-get install -y --only-upgrade "${packages[@]}"
  exit 0
fi
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg python3 git wireguard-tools
download() { curl --fail --show-error --silent --location --connect-timeout 15 --max-time 120 "$1"; }
if ! command -v docker >/dev/null 2>&1; then
  # Refuse to replace another container runtime or package family automatically.
  for package in docker.io podman-docker containerd runc; do
    if [ "$(dpkg-query -W -f='${db:Status-Status}' "$package" 2>/dev/null || true)" = installed ]; then
      printf 'Existing %s needs a deliberate Docker migration; nothing was removed.\n' "$package" >&2
      exit 2
    fi
  done
  sudo install -m 0755 -d /etc/apt/keyrings
  download https://download.docker.com/linux/ubuntu/gpg | sudo tee /etc/apt/keyrings/docker.asc >/dev/null
  sudo chmod a+r /etc/apt/keyrings/docker.asc
  printf 'deb [arch=%s signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu %s stable\n' "$(dpkg --print-architecture)" "$VERSION_CODENAME" | sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
if ! sudo docker compose version >/dev/null 2>&1; then
  sudo apt-get install -y docker-compose-plugin
fi
if ! command -v caddy >/dev/null 2>&1; then
  download https://dl.cloudsmith.io/public/caddy/stable/gpg.key | sudo gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  download https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  sudo apt-get update
  sudo apt-get install -y caddy
fi
sudo systemctl enable --now docker caddy
printf 'Infrastructure ready: Docker Engine, Caddy and WireGuard.\n'
