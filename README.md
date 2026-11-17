# CORE-AI

A Git-managed self-hosted AI workspace: **AnythingLLM + existing Ollama + direct WireGuard + Caddy + Docker Engine**.

The application and private connection use open-source components. There is no hosted VPN coordination service, VPN account, or required cloud AI provider. Package registries, Git hosting and normal public certificate issuance are distribution/TLS services, not model-inference services. The existing Windows operating system and hardware drivers are outside this application's open-source component claim.

## Why this stack

AnythingLLM is MIT licensed and runs in one application container with SQLite and embedded LanceDB. This avoids both Open WebUI's current branding-restricted license and adding a MongoDB dependency through a different dashboard. Ollama remains the existing model runtime. See [component licenses](docs/licenses.md).

Model files have their own licenses: an MIT-licensed runtime does not change the licenses of downloaded weights. Review each model separately. These scripts do not download or replace model weights.

## Initial deployment

| Component | Location | Persistence |
|---|---|---|
| Dashboard / accounts / documents / retrieval | Ubuntu VPS | `data-anythingllm/` and `runtime/anythingllm.env` |
| Model inference and existing weights | Windows laptop | Existing Ollama installation and model directory |
| Private network | Direct WireGuard between the two devices | Device-local private keys; public-key exchange over SSH |
| HTTPS | Existing VPS Caddy service | Managed site file plus backups of changed configuration |

The default private addresses are `10.203.0.1` (VPS) and `10.203.0.2` (laptop); confirm this range does not overlap another private network. Only the opposite peer's `/32` route is configured. Neither device sends general internet traffic through the tunnel. The laptop initiates to VPS UDP 51820 and uses a 25-second keepalive behind NAT. Allow UDP 51820 in any provider firewall. If UFW is already active, the installer adds only that UDP rule; it does not enable or reset UFW. DNS/HTTPS still require the selected hostname to point to the VPS and inbound 80/443.

## Migrate the earlier deployment

From the existing `~/core-ai` checkout:

```bash
git pull --ff-only origin main
./core-ai migrate --endpoint YOUR_VPS_PUBLIC_IPV4_OR_DNS
```

The migration reads the previous local domain and administrator credentials, backs up the previous data/settings and container metadata privately, prepares the WireGuard server, starts AnythingLLM on **localhost:3101**, creates/verifies the administrator in multi-user mode, rejects anonymous workspace access, and changes the Caddy upstream only after those checks pass. It then stops the old dashboard container. Existing Caddy sites are preserved, and only the exact CORE-AI site import is added when necessary.

The old `data/`, `.env`, backup and stopped container are retained. Conversations/documents are **not automatically converted** into the new application's database. Backups include secrets: do not upload or commit them. If deployment or publication fails, the old dashboard remains available at its prior local port; Caddy validation/reload failure restores prior Caddy files.

There is no automated chat conversion or full application rollback command yet. Do not delete the retained data or old container. The Caddy transaction and migration ordering are tested; a real restore drill remains an operations-phase acceptance item.

The new stack never invokes the old hosted VPN software. Existing global VPN software is not silently uninstalled because other host services may use it. Remove obsolete software separately after the replacement is verified.

## Fresh Ubuntu installation

Clone this repository to `~/core-ai`, then run as the normal deployment user:

```bash
./core-ai install --domain ai.example.com --endpoint YOUR_VPS_PUBLIC_IPV4_OR_DNS
```

Enter the administrator username and password when prompted. Missing prerequisites are installed from official apt repositories. Existing Docker Engine and Caddy installations are reused. No Kubernetes, extra database server, hosted AI gateway or cloud VPN account is required.

State layout:

- `config.env`: private deployment settings and bootstrap credentials, mode 0600, ignored by Git.
- `runtime/anythingllm.env`: persistent application dotenv file, owned by container UID 1000; includes stable JWT/encryption secrets and provider settings.
- `data-anythingllm/`: database, documents, keys and retrieval data; separate from legacy data.
- `/etc/wireguard/coreai.conf`: VPS-private tunnel key and enrolled laptop public key, root mode 0600.
- `backups/`: private, consistent application backups.

Provider settings changed in the application UI persist in its mounted dotenv file. An explicit `configure` command reapplies managed provider defaults; ordinary `update` does not reset them. Existing account passwords must be changed through the application's account flow, not by editing bootstrap credentials.

## Windows setup

In **PowerShell as Administrator**, from a separate checkout of this repository:

```powershell
git pull --ff-only origin main
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

Enter the VPS public address and SSH username. The script:

1. Installs WireGuard via winget if missing and enables the Windows OpenSSH client if needed.
2. Verifies that existing Ollama answers on localhost and has models.
3. Generates/reuses a private laptop key under the protected `%ProgramData%\CORE-AI\wireguard` directory.
4. Enrolls **only its public key** over SSH into the VPS checkout; SSH host-key checks remain enabled. SSH/sudo credentials may be requested locally.
5. Installs a persistent WireGuard tunnel service, preserving the key on reruns.
6. Adds an interface-bound TCP proxy from the laptop WireGuard address to localhost Ollama, with a Windows firewall allow rule scoped to the VPS peer address.

The script does not expose a public model endpoint, change Ollama's model path, route unrelated traffic, or request a VPN vendor login. If Ollama already has a wildcard listener, it stops before making a proxy and asks for that listener to be corrected. A default localhost Ollama installation needs no listener change. If a different laptop is already enrolled, the VPS refuses to overwrite its public key automatically.

The SSH account must have access to `~/core-ai` and sudo permission for the managed WireGuard interface. The laptop must stay awake and online for inference. The dashboard remains available when the laptop is offline.

## Verification and routine updates

On Ubuntu:

```bash
./core-ai doctor
./core-ai test-model
```

The generation check executes from inside the dashboard container. It uses the configured chat model and limits generated output. Use `--model MODEL_NAME` to test another installed model.

| Command | Purpose |
|---|---|
| `./core-ai update` | Fast-forward Git, back up current state, pull the pinned application image, redeploy |
| `./core-ai migrate --endpoint VPS_HOST` | Back up and switch the previous stack to the open-source deployment |
| `./core-ai configure` | Reapply local managed settings while preserving encryption secrets |
| `./core-ai deploy` | Apply existing application configuration |
| `./core-ai publish` | Validate authentication and safely publish the Caddy route |
| `./core-ai doctor` | Report WireGuard handshake, app health and model connectivity |
| `./core-ai logs` | Recent application logs |
| `./core-ai backup` | Briefly stop only the application, archive state/settings, resume |
| `./core-ai infra-update` | Explicit apt upgrades for installed Docker/Caddy/WireGuard packages |

Infrastructure upgrades can restart shared services, so they are separate from application updates and do not perform a blanket OS upgrade. Updates refuse a dirty source checkout and do not remove local changes.

## Later VPS inference migration

First size RAM/VRAM/disk for the actual selected models and workload. Then install compatible Ollama on the VPS, retain a backup, transfer or re-pull the exact selected weights, and reconfigure the provider using `host.docker.internal` if Ollama runs on the Docker host. The host listener and firewall must allow only the required container network. The domain and dashboard data remain the same. Verify generation with the laptop disconnected before retiring the tunnel.

## Project assistance

Use curated project code and documentation as workspace knowledge. Exclude broker credentials, private environment files and unrelated data. AI assistance is optional for the trading platform: no generated response is connected directly to order execution. Initial project access is read-only.

## Validation scope

Tests cover private configuration, stable secrets, input validation, scoped WireGuard routes, preservation of an enrolled peer, authentication gating, failed-migration ordering and Caddy rollback. CI also checks PowerShell syntax, Compose syntax and real Caddy parsing. Live Ubuntu migration, Windows service setup, peer handshake, model generation, public TLS and restoration must still be verified on the actual machines. A successful Git push is not a successful host deployment.
