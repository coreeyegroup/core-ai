# CORE-AI

Deployment documentation and diagnostic scripts for a self-hosted AI workspace using Open WebUI and Ollama.

## Architecture

- Open WebUI provides the browser interface, authentication, conversations and document workspace.
- Ollama serves existing local models on a separate computer initially.
- Tailscale provides private connectivity between the dashboard host and model host.
- Caddy provides the HTTPS reverse proxy on the dashboard host.
- A later migration can relocate Ollama and its model files, then update the dashboard provider connection.

Keep model storage separate from dashboard state. Accounts, conversations, settings and uploaded documents need persistent storage on the dashboard host. Moving model files alone does not move inference: evaluate memory, GPU support, storage and performance on the destination first.

This public repository contains reusable source and documentation only. Never commit credentials, private host inventories, access-policy exports, conversations, uploaded documents, model weights or backups.

## Build phases

| Phase | Scope | Completion criterion |
|---|---|---|
| 1. Foundation | Establish the repository and inspect existing software | Current setup recorded privately; existing installations preserved |
| 2. Private connection | Establish device visibility and private access to Ollama | Dashboard host and eventual container can list models and complete a short generation |
| 3. Dashboard | Deploy a pinned Open WebUI image, persistent state, authentication and HTTPS | Login and streaming chat work through the selected domain |
| 4. Project knowledge | Import curated code and documentation; configure retrieval | Answers reference the correct project sources |
| 5. Operations | Verify backups, restoration, updates and offline-provider behaviour | Recovery tested and maintenance procedures documented |
| 6. Inference migration | Provision a compatible destination and transfer models | Accepted inference performance with the original model host disconnected |

Authentication, a stable application secret, private bootstrap and persistent state are requirements for the first dashboard deployment. Backups must precede upgrades. The dashboard remains available when the model host is offline, but local inference cannot answer until its provider returns.

## Repository workflow

Implement and validate changes, push them to Git, then apply reviewed commands on the deployment host. A repository push is not evidence that the application is deployed. Keep host-specific configuration outside version control.

Use `~/core-ai` as the checkout directory. If that directory already exists and is empty, it can be used directly as the destination of a clone. If it contains files, inspect them before cloning or initializing a repository; do not overwrite them blindly.

After the initial clone, updates use:

```bash
cd ~/core-ai
git pull --ff-only origin main
```

## Available checks

Run the baseline inventory on Ubuntu:

```bash
bash scripts/check-ubuntu.sh
```

Run the private model connection check, replacing the argument with the model host's current Tailscale IPv4 address:

```bash
bash scripts/check-connection.sh LAPTOP_TAILSCALE_IP
```

Run the Windows inventory from a separate copy of this repository:

```powershell
powershell -NoProfile -File .\scripts\check-windows.ps1 -ProjectRoot 'YOUR_EXISTING_PROJECT_FOLDER'
```

All checks are read-only. They do not install services, change authentication or firewall settings, download models, or generate text. Inventory goes to the terminal; do not commit its output. Review personal device names and paths before sharing reports.

The connection check requires Python 3 and the Tailscale CLI. Exit 2 means a prerequisite failed. A successful model listing still requires a separate generation test and verification from the eventual dashboard container.

## Private connection troubleshooting

1. Run `tailscale status` and `tailscale switch --list` on both computers.
2. Compare active tailnets and confirm both devices appear in the selected network's admin console.
3. If a device is missing as a peer, review membership, device approval, key expiry and the scoped access policy. Different tailnets are one possible explanation; do not assume the cause from a timeout alone.
4. Once peer visibility works, inspect the Ollama listener, private port access and host firewall.
5. Verify model listing and generation from the deployment host and dashboard container.

Do not log an existing server out of Tailscale or replace access policies without understanding its current dependencies. Do not expose the unauthenticated Ollama API on the public internet. Keep the existing model directory intact.

## Deployment status

These files provide the repository foundation and connectivity checks. They do not deploy Open WebUI, configure DNS/Caddy, or resolve private network membership. Deployment configuration follows verification of those prerequisites.

## References

- https://docs.openwebui.com/getting-started/quick-start/
- https://docs.openwebui.com/getting-started/quick-start/connect-a-provider/starting-with-ollama/
- https://docs.ollama.com/faq
- https://tailscale.com/docs/reference/troubleshooting/connectivity/connect-device-failure
