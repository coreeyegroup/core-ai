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
./core-ai verify-backup
./core-ai publish
./core-ai infra-update
```

`update` refuses changed/untracked source, pulls main with fast-forward only, builds a new release, backs up the current PostgreSQL database and environment, and deploys. `infra-update` ensures the declared infrastructure exists; it does not perform a blanket Ubuntu/package upgrade. Backups contain private data/secrets and stay outside Git in root-only `backups/`.

A failed application/routing deployment restores the previous application release. Database migrations are forward-only and transactional; a failed deployment does not undo a successfully applied migration. This initial migration creates a new dedicated database rather than changing the previous dashboard database.

## Set the administrator login

After installing the custom workstation:

```bash
./core-ai set-login --username YOUR_USERNAME
```

Enter the desired password twice at the private prompts. This local sudo-authorized command renames the single administrator while preserving its identity and records, hashes the new password, clears lockout and revokes previous sessions. The explicit reset accepts 6–256 characters; fresh bootstrap retains its 12-character minimum. It does not store the password in Git, shell arguments or a configuration file. Pulling the updated scripts is sufficient; rebuilding the running application is not required for this command.

## Laptop setup

The transport remains direct WireGuard. No hosted VPN control plane is used. Run the following from the Git checkout in **Administrator PowerShell**:

```powershell
git pull --ff-only origin main
powershell -ExecutionPolicy Bypass -File .\setup.ps1 -VpsHost YOUR_VPS_HOST -VpsUser YOUR_UBUNTU_USER
```

The Windows installer installs missing WireGuard/OpenSSH, generates/preserves the laptop private key locally, enrolls only its public key through SSH, installs the project tunnel and exposes Ollama only to the VPS tunnel address through a restricted forwarding rule. The model process continues listening on Windows loopback. No models are downloaded or moved by this setup.

## Workspace release 1.2

The adopted workspace now includes unified navigation, Chat, Projects, Files, versioned Artifacts, source revisions, role and membership administration, model capability inspection, bounded model-directed task tools and observed execution metrics. Chat opens immediately without requiring a project or agent. All advanced panels remain available through grouped navigation and the command palette.

See [release behavior and limits](docs/release-1.2.md) and the [requirements register](docs/requirements-register.md) for implemented features, acceptance evidence and the remaining roadmap. A full coding sandbox, scheduled workflows, semantic retrieval, SSO and multimodal processing remain planned or unavailable. No control claims to perform these operations.


## Chat for general and professional work

- Start a new conversation, choose an installed text-generation model and send a message. No project or agent setup is required.
- Choose a model and a response style in the composer. Open Advanced for project and agent context, custom instructions, temperature, and maximum reply tokens.
- Replies stream into durable PostgreSQL message records. The browser refreshes the active reply incrementally; closing the browser does not cancel a generation.
- Stop keeps the partial reply. Regenerate and Edit & branch create a new conversation branch, preserving the original thread.
- Search conversations by text, status, or project. The conversation action menu supports rename, pin, archive/restore, and delete. Delete requires confirmation in the UI and is blocked while a reply is active. Export downloads the conversation as Markdown.
- Upload supported text/code, PDF text, DOCX or XLSX files; select up to eight processed library files for a message. Extracted excerpts are bounded to 32,000 combined characters. OCR, vision, web browsing and voice remain unavailable.
- Recent model context is bounded to 20 messages and 24,000 characters, plus system preferences and optional project excerpts. Large attachments may be excerpted; the full original text remains saved with the message. This is bounded local inference, not an unlimited context promise.
- Chat and professional tasks share one FIFO inference slot and a combined queue limit of 20. This protects the initial laptop deployment.
- Conversation history is private to its owning CORE-AI user. The UI keeps the selected conversation ID and layout preferences in browser storage; unsent drafts are held in session memory; messages and files remain in the product database.

## Security and independence

- Product-specific opaque, revocable, eight-hour sessions; scrypt password hashes, same-origin checks and CSRF tokens on mutations; login lockout after repeated failures.
- ADMIN/EDITOR/VIEWER account roles and project owner/editor/viewer memberships are checked on the server. Administrators manage local accounts; conversation histories remain owner-private. No public signup is exposed.
- No product-table sharing, broker credentials, host shell tool, Docker socket, root application process or mandatory cloud inference.
- Tools mode lets the model select only explicitly enabled, typed project tools. Every dispatch rechecks current permissions. Uploaded documents cannot grant access or enable a tool. No host shell or external product action is exposed.
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

### Multi-chat workspaces

Within **Chat**, use **+** in the Chats strip to add a conversation tab. Up to 12 conversation tabs fit in one Chat panel. Opening or closing one does not change the workbench layout; saved conversations remain in history. **New chat** opens a fresh tab when the active tab contains a saved conversation. **New split pane** and **Split workspace** are separate layout controls for opening another workbench group. The Explorer workspace selector switches between Build, Research, and Operations. Layouts and saved conversation tabs reopen in the same browser for the signed-in account, and unsent drafts stay in memory while the workspace is open.

Each chat can select its own installed model and response mode: General, Quick, Professional, Deep analysis, Research, or Coding. Modes change answer guidance. Local generation requests share the existing inference queue.

AI replies are left-aligned and your messages appear on the right. Use the arrow beside a message to collapse or expand it, or use **Collapse all** and **Expand all** above the conversation.
