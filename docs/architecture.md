# CORE-AI architecture — custom workstation baseline

## Independent product contract

CORE-AI, COREI-OS-MINI, Core Aura and every other product remain independently installable, deployable, authenticated, operable and recoverable. No other product must be running for CORE-AI to start. No other product must call CORE-AI to continue operating. A future connector outage degrades only the explicitly requested connected feature.

Each product owns its database, credentials, authorization, domain logic, service names, release lifecycle and backups. Connections use optional versioned APIs with explicit scopes, timeouts, disable controls and independently deployable adapters. SSO may be added as an optional identity interface; no shared parent-domain session cookie or copied password database.

## Reference alignment

Reviewed source: `coreeyegroup/corei-os-mini`, tree `8e746b2ae305593445e431dca29c00f620f02f43` on 2026-11-18. In particular `ui/src/App.tsx`, `layout.ts`, `appearance.ts`, `WorkbenchControls.tsx`, `themes.css`, `shell.css`, `scripts/install-workstation.sh`, `scripts/deploy-workstation.py` and the dedicated PostgreSQL configuration script.

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

This release implements a fixed tool workflow, not autonomous model-directed actions. It provides real persisted agent instructions, tasks, project knowledge retrieval, output artifacts and tool/audit records. It does not execute shell commands, open repositories automatically, push commits, place orders, publish APKs, change infrastructure or perform cross-product writes.

All authenticated accounts currently have the administrator tier. Project separation constrains retrieval context; it is not multi-tenant authorization. Expand permissions before adding other access tiers or external users.

## Extension order

1. Qualify this custom baseline on the deployment host and actual laptop models.
2. Add model-capability evaluations, context/token limits per model and task feedback.
3. Add constrained model-directed tools, explicit permission scopes and durable approval/reconciliation states as actions are introduced.
4. Add isolated repository workspaces and test execution without host root or production credentials.
5. Add optional COREI-OS-MINI API/context panels, initially read-only. Its risk, order, execution and reconciliation controls remain entirely with COREI-OS-MINI.
6. Add other optional product connectors after inspecting their actual contracts. Each connector stays disabled until configured and validated.
7. Move inference to capable VPS hardware by changing the private Ollama endpoint, then validate latency, memory and concurrency. Do not promise all large models fit the current VPS.

Workflows, scheduling, semantic search, workflow versioning, policy approvals, multi-user access administration and SSO require explicit implementation and qualification. The UI does not show fabricated working controls for these future features.

## Conversational workspace — release 1.1.0

The visual reference was refreshed against COREI-OS-MINI tree `45b6a0a5f5d6c65b25882ce411852a9294204bbf`. CORE-AI now uses the same font stack and dense measurement system: 12px UI text, 22px control/table rows, 32px title bar, 28px tabs, flat panel borders and 6px layout spacing. Chat preserves this typography with a bounded reading column.

`conversations`, `chat_messages` and `chat_generations` are added transactionally in migration 002. Every conversation is scoped to its owning user. Generation requests snapshot model/preferences, use unique client request identifiers for idempotent submission, and persist partial answers. Chat and task queues share the existing single worker and inference slot. The API never holds a streaming model request open for a browser: the durable worker performs inference, and the browser reads incremental persisted output.

Conversation state and agent-task state remain separate. General Chat does not create hidden projects or agents and does not imply tool execution. Project context is optional. Edited prompts and regenerated answers create non-destructive branches. Stop requests win over late successful output; worker lease expiry records an interrupted reply with its partial text retained.

The Chat/Workbench switch changes workspace presentation. It does not connect to any other product, change product permissions or create another deployment. The sidebar is available at all widths through an explicit toggle; mobile uses an overlay drawer.
