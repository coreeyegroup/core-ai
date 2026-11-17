#!/usr/bin/env bash
# Read-only baseline. Missing commands must not prevent the remaining checks.
set -u
section() { printf '\n%s\n' "$1"; }
run() { "$@" 2>&1 || printf 'UNAVAILABLE: %s\n' "$1"; }

section 'Operating system'
if [ -r /etc/os-release ]; then
  while IFS= read -r line; do
    case "$line" in PRETTY_NAME=*) printf '%s\n' "$line";; esac
  done < /etc/os-release
fi
run uname -m
section 'Resources'
run free -h
run df -h / /opt
if command -v nvidia-smi >/dev/null 2>&1; then
  run nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
else
  printf 'NVIDIA utility unavailable; no conclusion about GPU presence.\n'
fi
section 'Installed tools'
for tool in git docker caddy tailscale; do
  if command -v "$tool" >/dev/null 2>&1; then
    case "$tool" in
      caddy|tailscale) run "$tool" version;;
      *) run "$tool" --version;;
    esac
  else
    printf 'MISSING: %s\n' "$tool"
  fi
done
if command -v docker >/dev/null 2>&1; then
  section 'Compose and containers (names, images, ports only)'
  run docker compose version
  run docker ps -a --format '{{.Names}} | {{.Image}} | {{.Status}} | {{.Ports}}'
fi
section 'Tailscale IPv4 address'
if command -v tailscale >/dev/null 2>&1; then run tailscale ip -4; fi
section 'Listening TCP sockets'
run ss -ltn
section 'Service states'
if command -v systemctl >/dev/null 2>&1; then
  for svc in docker caddy tailscaled; do run systemctl is-active "$svc"; done
fi
section 'Caddy import statements (no credentials or full site contents)'
if [ -r /etc/caddy/Caddyfile ]; then
  while IFS= read -r line; do
    if [[ "$line" =~ ^[[:space:]]*import[[:space:]] ]]; then printf '%s\n' "$line"; fi
  done < /etc/caddy/Caddyfile
else
  printf 'Caddyfile absent or not readable by current user.\n'
fi
section 'Known potential deployment locations'
for directory in "$HOME/core-ai"; do
  if [ -d "$directory" ]; then
    printf 'FOUND: %s\n' "$directory"
    for file in compose.yaml compose.yml docker-compose.yml .env; do
      if [ -f "$directory/$file" ]; then printf 'PRESENT: %s\n' "$file"; fi
    done
  fi
done
section 'Completion'
printf 'Inventory only. Review UNAVAILABLE/MISSING entries; no configuration was changed.\n'
