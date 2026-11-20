# CORE-AI Workstation

An independent, self-hosted AI product with a custom workbench, API and durable task worker. CORE-AI operates without COREI-OS-MINI, Core Aura or any other product. Connections are optional versioned interfaces; each product keeps its own accounts, data, services, releases and recovery.

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
- Choose the model beside Send. Choose the response style, attachments and context in the toolbar below the prompt. Open Advanced for project and agent context, custom instructions, temperature, and maximum reply tokens.
- Replies stream into durable PostgreSQL message records. The browser refreshes the active reply incrementally; closing the browser does not cancel a generation.
- Stop keeps the partial reply. Regenerate and Edit & branch create a new conversation branch, preserving the original thread.
- Search conversations by text, status, or project. The conversation action menu supports rename, pin, archive/restore, and delete. Delete requires confirmation in the UI and is blocked while a reply is active. Export downloads the conversation as Markdown.
- Upload supported text/code, PDF text, DOCX or XLSX files; select up to eight processed library files for a message. Extracted excerpts are bounded to 32,000 combined characters. OCR, vision, web browsing and voice remain unavailable.
- Recent model context is bounded to 20 messages and 24,000 characters, plus system preferences and optional project excerpts. Large attachments may be excerpted; the full original text remains saved with the message. This is bounded local inference, not an unlimited context promise.
- Chat, professional tasks, and API jobs share one inference slot. When both queues have work, the worker alternates between workspace and API jobs, using oldest first within each group. The default queue holds 20 jobs with four slots reserved for workspace work. Operators can set `CORE_AI_QUEUE_CAPACITY` and `CORE_AI_WORKSPACE_QUEUE_RESERVE` in the private service environment. Keep both services on the same settings. File extraction runs independently in a bounded subprocess.
- Conversation history is private to its owning CORE-AI user. The UI keeps the selected conversation ID and layout preferences in browser storage; unsent drafts are held in session memory; messages and files remain in the product database.

## Connect an app, platform, or webhook

In CORE-AI, open **Manage → Connections → New connection** as an administrator. Name the connection and choose **Selected models** or **All supported installed models**. All-model access follows the installed Ollama catalog, including new supported models. Clear an individual model to block it, or use **Per-model overrides** to tighten request rate, pending jobs, timeout, context, and output limits. The connection-wide caps still apply. Set a default, lock the key to that model, or require the caller to specify a model. Text generation and text embedding each have their own submission permission. A project and an Analysis agent are optional. A linked project provides its instructions and matching sources, so select a project whose contents the receiving service may process.

Save the key in your service’s credential store. Select **Save encrypted copy for later reveal** when creating or rotating a key if you want to retrieve it from **API keys → View key**. Reveal requires your administrator password and records an audit event. Older keys and keys issued without recovery can be replaced through rotation. The installer provisions the encryption key in the private workstation configuration. Restore that configuration with the matching database snapshot to retain access to encrypted copies. The Connections panel can test an allowed model, view job metadata, pause or resume a key, rotate it, revoke it, and configure request and generation limits. Rotation expires the previous key immediately by default. An administrator can allow up to 24 hours of overlap and end it early from the connection menu. An already accepted job can finish after a pause or revocation. Existing single-model project keys keep their original model and scope when upgrading.

### REST API

Use any server-side HTTP client. Send `Authorization: Bearer YOUR_KEY` and, for JSON requests, `Content-Type: application/json`. The base URL is `https://ai.coreeye.in/api/v1/automation` on the production install.

| Method and path | Purpose |
|---|---|
| `GET /models` | List allowed generation models and the default. Use `?operation=embedding` for embedding models. A fixed-model key returns only its compatible default. |
| `GET /model-policies` | Read effective limits for permitted models. Accepts the same `operation` parameter. |
| `POST /jobs` | Submit JSON such as `{"request_id":"summary-123","prompt":"Summarize the notes.","model":"qwen3:4b"}`. Omit `model` if the connection has a default. HTTP `202` returns a job `id`. |
| `POST /embeddings` | Queue one text embedding. Send `request_id`, `input`, and an eligible `model` or use the configured default. Enable embedding submission on the key. |
| `GET /jobs/{id}` | Read status and the successful `output` or `embeddings`. Poll with the same key and bounded retries. Stop at `SUCCEEDED`, `FAILED`, or `CANCELLED`. |
| `POST /jobs/{id}/cancel` | Cancel a queued job or request cooperative cancellation of a running job. Requires key cancellation permission. |
| `POST /jobs/{id}/retry` | Send a new `request_id` to rerun a failed or cancelled job under current permissions and limits. |
| `GET /usage` | Read 30-day model usage and pending jobs. Token totals are provider measurements. Requires result access. |
| `GET /openapi.json` | Download the versioned automation API schema. |

When retrying an HTTP submission after a transport failure, send the same request ID and payload. A changed explicit model or prompt for that ID returns `409`. On a submission rate limit, respect `Retry-After`. For Make, Zapier, n8n, or a similar platform, configure an HTTP action with the same method, URL, headers, and JSON. In n8n use **HTTP Request → Generic Credential Type → Header Auth**.

### Webhooks

- **Inbound** — Any webhook client that can supply the Bearer header and transform its JSON can call `POST /jobs`. Use its stable event ID for `request_id` and map the text you want processed to `prompt`. Providers that send only a fixed payload or their own signatures need an intermediary to verify the provider event and make the CORE-AI API call.
- **Outbound** — In a connection, choose a named destination under **Job completion webhook**. CORE-AI POSTs a `job.finished` event when a job succeeds, fails, or is cancelled. The payload contains a stable event ID, the job ID, request ID, model, terminal status, and finish time. Fetch the result via the job API when needed. Prompt and result text are absent from callbacks.
- **Provisioning** — A server operator adds `CORE_AI_WEBHOOK_EVENTS_URL=https://receiver.example/webhook` and `CORE_AI_WEBHOOK_EVENTS_SECRET=YOUR_RANDOM_SIGNING_SECRET` to the workstation’s private service environment at `/etc/core-ai/workstation.env`. Replace `EVENTS` in both names for each destination and use a signing secret of at least 32 characters. After provisioning, restart both services with `sudo systemctl restart core-ai-api core-ai-worker`. The UI exposes destination names. Provision only HTTPS endpoints that you trust to receive job metadata.
- **Verification and retries** — Compare `X-Core-AI-Signature` with `sha256=` plus the hex HMAC-SHA256 of `X-Core-AI-Timestamp + "." + raw request body`, using the configured secret and a constant-time comparison. Reject stale timestamps. Deduplicate by event ID. Delivery happens independently of inference and retries transient failures up to three total attempts. Delivery status appears in Recent activity. An administrator can replay a failed or cancelled delivery if its original destination remains configured and active. A replay keeps the event ID and uses a fresh signature timestamp.

## Work inside a project

Search the Projects directory and open or create a project to see its focused workspace. Use **All projects** to return to the directory. Project sections include Chats, Sources, Instructions, Artifacts, Members, and Settings. Start a new chat from the project to preselect its context and any project model or response-style defaults. Moving a chat changes context for future replies and keeps the conversation private to its owner. Project sources and explicitly shared artifacts follow project membership. Owners and administrators can archive or restore projects from Settings. Archived projects remain readable and can be restored before accepting new project work.

## Security and independence

- Product-specific opaque, revocable, eight-hour sessions; scrypt password hashes, same-origin checks and CSRF tokens on mutations; login lockout after repeated failures.
- ADMIN/EDITOR/VIEWER account roles and project owner/editor/viewer memberships are checked on the server. Administrators manage local accounts; conversation histories remain owner-private. No public signup is exposed.
- No product-table sharing, broker credentials, host shell tool, Docker socket, root application process or mandatory cloud inference.
- Tools mode lets the model select only explicitly enabled, typed project tools. Every dispatch rechecks current permissions. Uploaded documents cannot grant access or enable a tool. No host shell or external product action is exposed.
- The model endpoint accepts explicit private/loopback IPv4 addresses only; redirects and inherited proxy variables are disabled.
- Interrupted worker leases become visible failed or cancelled tasks. A cancellation requested during inference prevents a later success from being published. An artifact committed before cancellation remains visible in the task step history.
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
