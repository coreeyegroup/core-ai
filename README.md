# CORE-AI

Git-managed installation, configuration and updates for a self-hosted AI workspace using Open WebUI and Ollama.

## Install on Ubuntu

From the checked-out repository, run as the normal deployment user:

```bash
./core-ai install --domain ai.example.com --model-host LAPTOP_TAILSCALE_IPV4
```

The installer requests sudo for package and service operations. It installs missing prerequisites from official apt repositories, reuses existing Docker/Caddy/Tailscale installations, prompts for the administrator email and password, saves local configuration with mode 0600, starts Open WebUI, verifies the administrator exists before publishing, and installs the HTTPS route. Existing services are not removed. Conflicting container package families require explicit migration rather than automatic removal.

Set the selected domain's DNS to the deployment server and make ports 80/443 reachable. The installer cannot change a DNS provider account without its credentials. It reports a pending HTTPS check if DNS or certificate issuance is not ready.

Open WebUI uses a release tag pinned in `compose.yaml`. Dashboard state lives under `data/`; host settings and secrets live in `.env`. Neither is committed. Raw env-file parsing preserves literal password characters. Compose must support `env_file.format: raw` (Compose 2.30+). The first install can deploy the dashboard even if the model laptop is disconnected; inference remains pending.

## Set up the Windows model connection

Keep existing Ollama and models in place. From a separate checkout of this repository, run PowerShell as Administrator:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup-windows.ps1 -Tailnet 'YOUR_TAILNET_NAME'
```

The script installs Tailscale via winget if missing, checks/selects the requested authenticated profile, verifies the existing localhost Ollama model listing, and configures private Tailscale Serve TCP forwarding. It does not change Ollama's listener or model directory. The existing tailnet access policy controls which members can reach the forwarded port. No public Funnel is configured.

Account sign-in, account selection, MFA and device approval can require the account owner's interaction. The script initiates the sign-in flow if the requested profile is not yet authenticated. Complete the displayed link using the correct account and rerun if the login timeout expires. It does not log the server out or weaken the tailnet policy.

## Daily commands

| Command | Action |
|---|---|
| `./core-ai install` | Install missing infrastructure, configure, deploy and publish |
| `./core-ai update` | Fast-forward source, back up state, pull the pinned image and redeploy |
| `./core-ai configure` | Update local domain/provider configuration; preserve administrator credentials and secret |
| `./core-ai deploy` | Apply existing local settings to the dashboard |
| `./core-ai publish` | Validate and publish the Caddy route; restore prior files if validation/reload fails |
| `./core-ai doctor` | Report dashboard and private model connection health |
| `./core-ai logs` | Show recent dashboard logs |
| `./core-ai backup` | Stop only this dashboard briefly, archive its state/settings, and resume it |
| `./core-ai test-model --model MODEL_NAME` | Run bounded generation through the dashboard container against an installed model |
| `./core-ai infra-update` | Explicitly upgrade installed Docker, Caddy and Tailscale apt packages |

An infrastructure update can restart shared host services. It is separate from application updates and does not run a blanket OS upgrade. Installation preserves the VPS's active Tailscale account. For a new unauthenticated VPS, complete the sign-in link from `sudo tailscale up` once.

Updates refuse a dirty source checkout and do not reset local changes. Backups contain secrets and private data: keep them private. Before a database-migrating upgrade, retain its backup and prior image reference. Backup creation is implemented; automated restoration and a full restore drill remain part of the operations phase.

Application configuration is managed by `.env`: `ENABLE_PERSISTENT_CONFIG=false` makes those settings authoritative. Admin settings changed only in the UI may revert at restart. Accounts, chats, documents and other database entities remain persistent. Changing the bootstrap password in `.env` does not reset an existing account password; use the application's password-change flow.

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

After the initial clone, application updates use:

```bash
cd ~/core-ai
./core-ai update
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

The `check-*` scripts are read-only. They do not install services, change authentication or firewall settings, download models, or generate text. Inventory goes to the terminal; do not commit its output. Review personal device names and paths before sharing reports. Installation/setup commands are separate and do change the requested deployment.

The connection check requires Python 3 and the Tailscale CLI. Exit 2 means a prerequisite failed. A successful model listing still requires a separate generation test and verification from the eventual dashboard container.

## Private connection troubleshooting

1. Run `tailscale status` and `tailscale switch --list` on both computers.
2. Compare active tailnets and confirm both devices appear in the selected network's admin console.
3. If a device is missing as a peer, review membership, device approval, key expiry and the scoped access policy. Different tailnets are one possible explanation; do not assume the cause from a timeout alone.
4. Once peer visibility works, inspect the Ollama listener, private port access and host firewall.
5. Verify model listing and generation from the deployment host and dashboard container.

Do not log an existing server out of Tailscale or replace access policies without understanding its current dependencies. Do not expose the unauthenticated Ollama API on the public internet. Keep the existing model directory intact.

## Deployment status

The repository includes the installer, pinned Compose deployment, local configuration wizard, Caddy route management, backup/update commands and a Windows private-connection setup script. Live DNS ownership, identity-provider authorization and device approval remain external prerequisites. A source push is not proof of a successful host installation.

Validation covers shell syntax, configuration/secret handling and Caddy rollback behaviour. GitHub Actions also validates Compose syntax. Live Ubuntu deployment, Windows execution, inference, TLS and a restore drill require verification on the actual machines.

## References

- https://docs.openwebui.com/getting-started/quick-start/
- https://docs.openwebui.com/getting-started/quick-start/connect-a-provider/starting-with-ollama/
- https://docs.ollama.com/faq
- https://tailscale.com/docs/reference/troubleshooting/connectivity/connect-device-failure
