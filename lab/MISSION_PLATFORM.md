# CORE-AI consolidated mission platform

## What this release changes

This release preserves existing Chat, Tasks, research workflows, projects,
models, repository lab, connection APIs, and all qualified offline programs.
It adds one shared model tool loop with administrator budgets and current
permission intersections; durable program jobs shared by Chat/Tasks/manual
runs; saved dependency missions with conditional steps and checkpoint controls;
guided program parameters, owner-scoped history, explicit retry and downloads;
and a reviewed agent factory and scoped external program API.

Existing explicitly granted broad program permissions are migrated as a
wildcard; new profiles default to no recipe access. New external program
scopes default to empty. No provider, broker, plugin or third-party installer
is automatically authorized.

## Deployment

Pull the same reviewed main commit into both checkouts. Review migration
022_mission_platform.sql and this document. Back up and deploy with the
existing approved integration installer:

    cd ~/core-ai && git pull --ff-only origin main
    cd ~/core-ai-lab/manager && git pull --ff-only origin main
    git log -1 --oneline
    bash lab/install-integration.sh --approve-deploy

The command restarts the gateway, checks the previous 26 receipts, exercises
the known real position-sizing fixture, and invokes the existing application
installer. This is a database migration and service deployment: operator
approval is required. Do not run if CI has not passed or while important
jobs are running. Database changes are additive; do not edit applied
migration checksums. Use the normal backup/recovery procedure.

## Workflow

1. Models: configure execution budgets and optional operator-defined model
   size cap; this cap is not live free RAM or VRAM telemetry.
2. Tools: select a program, enter guided parameters or advanced JSON,
   submit a job, inspect persisted history and download results.
3. Agents: choose Tools mode, program.list/program.run and exact recipe
   scope (or explicitly permit all qualified programs).
4. Chat/Tasks: use the existing permitted agent. Both use the same
   tool-call loop and durable program jobs. They retain separate history
   presentation. Tool calls cannot change their own permissions.
5. Workflows: save a Mission with project, objective, explicit agents or
   programs, inputs and dependency IDs. Start the exact saved version.
   Independent steps currently execute in listed topological order on the
   constrained host. Agent steps receive bounded dependency output.
   Program inputs may reference dependency values with a structured
   object containing $step and path. A condition may compare a dependency
   path to an exact JSON value. A false condition skips the step.
   Pause stops at a checkpoint; retry preserves completed children;
   cancellation requests propagate to the current child. Inspect actual
   child evidence, not only the model narrative.
6. Agent factory: run a task asking for a JSON object with name,
   instructions, runtime_mode, tools and explicit program_scope. Import
   the successful task output as a draft, review its digest and publish a
   disabled agent. Enable after manual review, run a qualification task,
   and attach reviewer notes to that exact agent version. Success status
   alone does not establish semantic quality.
7. Connections: for existing API keys, expand Offline program API
   permissions. Select exact non-file recipes. Existing discover, submit,
   read and cancel flags still apply. Example API flow:
   GET /api/v1/automation/programs
   POST /api/v1/automation/programs/jobs with a UUID request_id, recipe,
   and values JSON array; poll GET /api/v1/automation/programs/jobs/ID.
   Existing model APIs and n8n integrations remain independent.
   API keys are not exposed to models, logged, or passed to containers.

## MCP bridge and native hosts

The local stdio bridge uses the MCP 2025-11-25 initialization lifecycle,
tools/list and tools/call. It is intentionally limited to the existing
scoped offline-program API. It is not a general inbound MCP client or a
claim of certification against every MCP host/protocol version.
Launch from a compatible host with a separately scoped key passed via
CORE_AI_PROGRAM_API_TOKEN (not command arguments or committed config):

    python3 /home/coreeye/core-ai-lab/manager/lab/mcp_stdio.py --origin https://ai.coreeye.in --allow position-sizing

The bridge requires HTTPS, never follows redirects, accepts exact program
IDs, and does not expose shell, file upload, broker orders or arbitrary
network calls. If a call times out its job remains inspectable. See official
MCP SDK protocol compatibility and OpenCode MCP server configuration:
https://py.sdk.modelcontextprotocol.io/whats-new/
https://opencode.ai/docs/mcp-servers/

Tools shows native image/probe evidence for OpenCode/Superpowers.
Run the already implemented native review and probe against the existing
image only after operator review:

    python3 lab/native_host.py review
    # Use the exact reviewed digest after approval.
    python3 lab/native_host.py verify --approve REVIEWED_DIGEST

Skill visibility is not functional model-driven native qualification.
Full native agent dispatch, arbitrary inbound MCP servers, autonomous
planning/install, live data providers and full upstream installation
remain separate unqualified capability classes. The repository lifecycle
review provides verified candidate entry points and missing work for all
24 pins, not a false full-installation status:

    python3 lab/installation_review.py

## Safety and recovery

Program jobs are pinned to exact source and image. A running tracked
gateway process supports cooperative cancellation and attempts to kill
its named container; test actual daemon/container cancellation on the
target host. Model cancellation is checked at response and tool
boundaries; it cannot guarantee interruption while the provider is
blocked. Lease expiration marks work interrupted, never silently reruns
it. Retry is explicit. A single program slot is retained for the existing
VPS; the durable queue is separate from the inference worker. History has
bounded storage and per-account job limits; automated retention/export
policy and distributed workers are still pending. Manual results are
persisted in program history; agent-generated files continue to enter
the file library. Do not submit secrets as numeric/JSON arguments.

## Acceptance

Check owner/project/connection isolation; revoke a recipe while queued;
cancel an active job; refresh/restart before result retrieval; run a two
step mission and retry after a failed child; compare manual, Chat, Task,
and connection program outputs; verify legacy research and n8n.
Use actual local model and Docker runtime for deployment acceptance.
A passing mocked CI fixture is not a substitute for those live tests.
