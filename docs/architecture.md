# CORE-AI architecture — independent workspace 1.2

## Independent product contract

CORE-AI, COREI-OS-MINI, Core Aura and every other product remain independently installable, deployable, authenticated, operable and recoverable. No other product must be running for CORE-AI to start. No other product must call CORE-AI to continue operating. A future connector outage degrades only the explicitly requested connected feature.

Each product owns its database, credentials, authorization, domain logic, service names, release lifecycle and backups. Connections use optional versioned APIs with explicit scopes, timeouts, disable controls and independently deployable adapters. SSO may be added as an optional identity interface; no shared parent-domain session cookie or copied password database.

## Reference alignment

Reviewed source: `coreeyegroup/corei-os-mini`, tree `620d14fe2aaf9ef8d14bf1e606427273037ed177` on 2026-11-18. In particular `ui/src/App.tsx`, `layout.ts`, `appearance.ts`, `WorkbenchControls.tsx`, `themes.css`, `shell.css`, `scripts/install-workstation.sh`, `scripts/deploy-workstation.py` and the dedicated PostgreSQL configuration script.

Reused/adapted shell controls, icon strokes and theme tokens from that user-owned reference. CORE-AI has a smaller independent shell implementation and its own module content. No trading backend, database tables, order operations, secrets or mandatory runtime calls were copied. Future reference changes do not automatically alter CORE-AI.

| Layer | CORE-AI choice | Reference alignment |
| --- | --- | --- |
| Browser | Custom React 19.3.1 / TypeScript / Vite 8 | Same workbench technology/patterns |
| UI state | Versioned local layouts and appearance | Separate CORE-AI keys; detached views do not overwrite main layout |
| API | FastAPI modular Python application | Own product identity and `/api/v1` contract |
| Database | PostgreSQL 18, dedicated cluster/database/role, port 5434 | Same dedicated-cluster approach; distinct resources |
| Background jobs | Same-codebase native worker | Durable PostgreSQL queue, no extra queue infrastructure |
| Runtime | Isolated Python 3.14.10 / Node 26.13.0 | Same selected toolchain versions; own installation paths |
| Process management | systemd | Own restricted API/worker service account and units |
| Edge | Existing Caddy | Only CORE-AI site managed, complete configuration validation |
| Inference | Ollama adapter over private WireGuard | Existing verified transport, independent model location |
| Release | Git-managed installer and immutable release pointers | Build, health-check, switch, rollback |

## Runtime flow

Authenticated user → API validates origin/session/CSRF → project/agent validation → queue row snapshots the agent instructions/version → worker claims one task → project-only full-text retrieval records source IDs → private Ollama inference → cancellation/state reconciliation → persisted task output and audit → workspace reads the result.

The database claim uses transaction locking and `FOR UPDATE SKIP LOCKED`. Network calls happen outside a database transaction. A separate worker heartbeat renews the executing task lease. A session advisory lock prevents multiple installed workers from executing concurrently. Expired tasks are explicitly failed/cancelled; they are not silently replayed.

Task states: `QUEUED`, `RUNNING`, `CANCEL_REQUESTED`, `CANCELLED`, `SUCCEEDED`, `FAILED`. Cancellation is checked between provider chunks and at final result commit. Provider reads have a timeout; a cancellation request may wait for the active read to return. Cancellation never promises to physically stop the remote model process immediately.

## Current boundaries

Analysis mode retrieves project sources and generates a response. Tools mode uses a bounded model-directed loop restricted to explicitly enabled typed project tools; every call rechecks current actor/project permissions. It provides versioned agent definitions, durable task steps, project knowledge, file ingestion and revisioned artifacts. It does not execute shell commands, open repositories automatically, push commits, place orders, publish APKs, change infrastructure or perform cross-product writes.

ADMIN/EDITOR/VIEWER are server-enforced account roles. Project memberships determine source/task access; administrators have project administration privileges. Private conversations remain owner-scoped; artifacts have explicit private/project visibility. This is project authorization within one deployment, not infrastructure-level tenant isolation.

## Extension order

1. Qualify this custom baseline on the deployment host and actual laptop models.
2. Add model-capability evaluations, context/token limits per model and task feedback.
3. Extend the existing typed project tools only after adding explicit approval and reconciliation states for external actions.
4. Add isolated repository workspaces and test execution without host root or production credentials.
5. Add optional COREI-OS-MINI API/context panels, initially read-only. Its risk, order, execution and reconciliation controls remain entirely with COREI-OS-MINI.
6. Add other optional product connectors after inspecting their actual contracts. Each connector stays disabled until configured and validated.
7. Move inference to capable VPS hardware by changing the private Ollama endpoint, then validate latency, memory and concurrency. Do not promise all large models fit the current VPS.

Workflows, scheduling, semantic search, workflow versioning, policy approvals and SSO require explicit implementation and qualification. The UI does not show fabricated working controls for these future features.

## Conversational workspace — release 1.1.0

The visual reference was refreshed against COREI-OS-MINI tree `45b6a0a5f5d6c65b25882ce411852a9294204bbf`. CORE-AI now uses the same font stack and dense measurement system: 12px UI text, 22px control/table rows, 32px title bar, 28px tabs, flat panel borders and 6px layout spacing. Chat preserves this typography with a bounded reading column.

`conversations`, `chat_messages` and `chat_generations` are added transactionally in migration 002. Every conversation is scoped to its owning user. Generation requests snapshot model/preferences, use unique client request identifiers for idempotent submission, and persist partial answers. Chat and task queues share the existing single worker and inference slot. The API never holds a streaming model request open for a browser: the durable worker performs inference, and the browser reads incremental persisted output.

Conversation state and agent-task state remain separate. General Chat does not create hidden projects or agents and does not imply tool execution. Project context is optional. Edited prompts and regenerated answers create non-destructive branches. Stop requests win over late successful output; worker lease expiry records an interrupted reply with its partial text retained.

The Chat/Workbench switch changes workspace presentation. It does not connect to any other product, change product permissions or create another deployment. The sidebar is available at all widths through an explicit toggle; mobile uses an overlay drawer.

## Workspace migration 003 — release 1.2

Migration 003 adds roles, project ownership/membership/instructions, file queue and raw/extracted content, versioned sources/artifacts, per-task tools and measured runtime counters. It preserves the 001/002 checksums and is additive for the previous release. Upload parsing runs in the restricted worker; unconfigured formats fail visibly. A separate library/editor supports optimistic revisions and safe Markdown previews. The unified sidebar stays present across panels; advanced groups collapse without removing capabilities. Header height is 42px; compact UI rows remain 22px and conversation reading text defaults to 14px independently of the 12px controls.

See [release behavior and limits](release-1.2.md) for resource caps, tool budgets, recovery checks and remaining work.
