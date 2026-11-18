# CORE-AI Workstation

An independent, self-hosted AI product with a custom workbench, API and durable task worker. CORE-AI operates without COREI-OS-MINI, Core Aura or any other product. Future connections are optional versioned interfaces; each product keeps its own accounts, data, services, releases and recovery.

## Install on Ubuntu

Ubuntu 22.04/24.04 x86_64. Run as a normal user with sudo from the repository checkout:

```bash
git pull --ff-only origin main
./core-ai install --domain ai.example.com --endpoint VPS_PUBLIC_IP
```

The installer asks for missing configuration. It reuses the previous locally configured domain, private model host and administrator credentials when migrating. On a fresh installation it asks for the administrator username and password. Passwords and keys do not belong in Git.

The complete infrastructure/build/deploy sequence is in this repository:

1. Archive previous dashboard configuration/data consistently, briefly stopping only the old CORE-AI containers and restarting them afterward.
2. Install missing Caddy, PostgreSQL 18 and WireGuard packages from their official repositories. Preserve existing system Python, Node and other applications.
3. Install checksum-verified project Node 26.13.0 and Python 3.14.10 under `/opt/core-ai/toolchain`. Python is compiled with two jobs if absent; the first installation can take time.
4. Build React/TypeScript with `npm ci`; build an independent Python environment in a new release directory.
5. Create only PostgreSQL `18/core_ai` at loopback port **5434**, database `core_ai`, restricted role `core_ai_app`. Other PostgreSQL clusters/databases are not modified. Refuse an occupied port or unexpected cluster identity.
6. Apply checksummed migrations. Seed the first administrator only; subsequent installs do not reset passwords.
7. Install unprivileged `core-ai-api` and `core-ai-worker` systemd services; API binds **127.0.0.1:18787**.
8. Verify backend identity, database connectivity, anonymous-access rejection and worker heartbeat.
9. Switch immutable UI/API release pointers and validate/reload only the managed CORE-AI Caddy route. On failure restore the prior route, pointers and service units.
10. Stop superseded CORE-AI dashboard containers after successful cutover. Keep their data and archives for review.

DNS must point the configured domain to the VPS and inbound TCP 80/443 must be permitted. The installer validates local routing; `doctor` additionally checks public HTTPS. Existing WireGuard enrollment/keys are preserved; UDP 51820 is needed for laptop inference.

## Update and operate

```bash
cd ~/core-ai
./core-ai update
./core-ai doctor
./core-ai test-model
```

Other commands:

```bash
./core-ai logs
./core-ai backup
./core-ai publish
./core-ai infra-update
```

`update` refuses changed/untracked source, pulls main with fast-forward only, builds a new release, backs up the current PostgreSQL database and environment, and deploys. `infra-update` ensures the declared infrastructure exists; it does not perform a blanket Ubuntu/package upgrade. Backups contain private data/secrets and stay outside Git in root-only `backups/`.

A failed application/routing deployment restores the previous application release. Database migrations are forward-only and transactional; a failed deployment does not undo a successfully applied migration. This initial migration creates a new dedicated database rather than changing the previous dashboard database.

## Laptop setup

The transport remains direct WireGuard. No hosted VPN control plane is used. Run the following from the Git checkout in **Administrator PowerShell**:

```powershell
git pull --ff-only origin main
powershell -ExecutionPolicy Bypass -File .\setup.ps1 -VpsHost YOUR_VPS_HOST -VpsUser YOUR_UBUNTU_USER
```

The Windows installer installs missing WireGuard/OpenSSH, generates/preserves the laptop private key locally, enrolls only its public key through SSH, installs the project tunnel and exposes Ollama only to the VPS tunnel address through a restricted forwarding rule. The model process continues listening on Windows loopback. No models are downloaded or moved by this setup.

## Custom application capabilities

| Workbench panel | Implemented operation |
| --- | --- |
| Overview | Database-backed project/agent/document/task counts and worker heartbeat |
| Projects | Create and list separate project contexts |
| Agents | Create, edit, disable and version agent instructions; tasks snapshot instructions/version |
| Tasks | Submit, list, inspect, cancel; durable queue, one inference slot, interrupted-lease detection |
| Knowledge | Save/import text or Markdown under a project, list/delete documents; project-scoped full-text retrieval |
| Artifacts | Inspect/download persisted completed task outputs |
| Models | List the real Ollama model inventory; configure private endpoint/default model |
| Tools | Inspect enabled backend capabilities and their limitations |
| Integrations | Inspect independent-product connection policy and actual connected count (zero initially) |
| Operations | Persisted audit/tool lifecycle events |
| Settings | Themes, text size, density, rail/status visibility and tab wrapping |

The shell follows COREI-OS-MINI's workbench patterns: grouped navigation, explorer, tab groups, up to four splits, inspector, activity/runtime panel, keyboard command palette, pin/close/open-alone/detach controls, saved workspace layouts, themes and narrow-screen behavior. The application operations, database and service identity are CORE-AI's own.

This release implements a **fixed retrieval → local inference workflow**, using a versioned agent's instructions. It is the custom foundation for an agent platform. Model-directed tool loops, coding sandboxes, external product actions, scheduled workflows, semantic embeddings, multi-user role administration and SSO are **not implemented** and are not presented as working controls. Existing documents/chat histories from third-party dashboards are archived, not automatically converted.

The local model list is discovery, not a capability certification. Do not use embedding models for generation. Model failures are recorded, not replaced with fabricated results. Output is displayed as text, not executable HTML.

## Security and independence

- Product-specific opaque, revocable, eight-hour sessions; scrypt password hashes, same-origin checks and CSRF tokens on mutations; login lockout after repeated failures.
- This release has a single administrator access tier. All signed-in administrators can access all CORE-AI projects; projects are organizational contexts, not tenant security boundaries. No user invitation API is exposed.
- No product-table sharing, broker credentials, host shell tool, Docker socket, root application process or mandatory cloud inference.
- Tool dispatch is fixed in backend code, not decided by instructions inside uploaded documents. Only project retrieval and bounded model generation are enabled.
- The model endpoint accepts explicit private/loopback IPv4 addresses only; redirects and inherited proxy variables are disabled.
- Interrupted worker leases become visible failed/cancelled tasks. A model answer arriving after a cancellation cannot publish a successful output. Submit a new task deliberately to retry.
- Server secrets are root-only in `/etc/core-ai/workstation.env`. Application data is in its dedicated PostgreSQL cluster. systemd passes configuration to the unprivileged service account.
- Logs/audit are local. There is no application telemetry or third-party dashboard runtime.

## Repository and runtime structure

```text
ui/                         React + TypeScript + Vite workstation
backend/src/core_ai/        FastAPI, sessions, PostgreSQL, model adapter, worker
backend/sql/                Checksummed transactional migrations
backend/tests/              PostgreSQL-backed API/runtime/security integration tests
scripts/                    Infrastructure, immutable releases, routing, administration
scripts/setup-windows.ps1   Private model transport enrollment
scripts/network.py          Direct WireGuard utility
setup.ps1                   Short Windows launcher
core-ai                     Stable Ubuntu command entry point
deploy/                     Caddy template
tests/                      Deployment/transport checks
```

Runtime paths:

```text
/opt/core-ai/toolchain/       Independent Node and Python
/opt/core-ai/releases/        Built releases, each with its own Python environment
/opt/core-ai/current          Active application release pointer
/var/www/core-ai-workstation/current   Active UI release pointer
/etc/core-ai/workstation.env Root-only application environment
/var/lib/postgresql/18/core_ai         Dedicated database cluster
/var/lib/core-ai/             Reserved private application storage
/etc/caddy/sites/core-ai.caddy        Managed web route
/etc/wireguard/coreai.conf    Existing private tunnel; preserved
```

## Development and checks

Production installation pins the same runtime versions selected by the reference workstation. Source also supports Python 3.12+ for development/testing. Use a **disposable CORE-AI test database**: tests truncate their own tables.

```bash
python3 -m venv .venv-dev
.venv-dev/bin/pip install -e './backend[test]'
# Supply CORE_AI_DATABASE_URL for a disposable PostgreSQL database.
.venv-dev/bin/python -m pytest backend/tests tests -q
npm ci --prefix ui
npm run build --prefix ui
npm test --prefix ui
```

CI uses PostgreSQL 18 and validates the Caddy template. The UI dev server is optional (`npm run dev --prefix ui`) and proxies `/api` to the loopback API. Set `CORE_AI_ORIGIN` to that dev server's exact origin when running a local backend; production always uses the configured HTTPS origin.

See [architecture](docs/architecture.md), [migration and recovery](docs/migration.md) and [software licenses](docs/licenses.md).
