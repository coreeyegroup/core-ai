# Native and master platform upgrade

This release extends the existing mission and independent-program architecture; it does not change the existing 38 qualification receipts.

## Master planning
Choose a project, planner profile, generation model, objective and explicit agent/program allowlist under Workflows → Master planner. The job is queued as analysis-only, with no program or action tools. It must return a valid mission with selected capability IDs and topologically ordered dependencies. Review the exact plan and versions, approve to save a mission, then launch separately. Generated drafts cannot authorize new capabilities. Editing the saved mission manually uses the existing manual workflow controls. The single inference worker remains in place; parallel inference, automatic replanning and shared memory are not enabled by this change.

## Native profiles
The old Superpowers probe remains available for comparison. The new profiles use separate read-only pinned source mounts, disposable home and workspace, no network or Docker socket, and documented local discovery loaders. The two supported configured-directory routes are an alternative when discovery fails. Run on the server after reviewing the exact plan:

    python3 lab/native_profiles.py review superpowers
    # Copy exact digest only after review:
    python3 lab/native_profiles.py verify superpowers --approve REVIEWED_DIGEST
    python3 lab/native_profiles.py review ponytail
    python3 lab/native_profiles.py review i-have-adhd
    python3 lab/native_profiles.py status

Repeat verify for each separately reviewed profile. If directory-form registration is needed, add --route directory to both review and verify for Superpowers or Ponytail. ADHD uses the documented discovery loader. Observed plugin and skill IDs must both match. Registration does not establish model-driven execution. No personal Claude, Codex or OpenCode config is modified.

## Resource observations
Models reports server CPU, memory and disk, plus remote Ollama's loaded-model size and VRAM allocation. It deliberately does not claim the remote provider's total/free GPU memory. Existing model-size cap remains configurable.

## Evidence and deployment
Run full CI before promoting. Deploy with the existing integration installer after explicit operator approval, pulling identical main commits into both checkouts. Migration 023 is additive. Actual native profile and model execution tests require Ubuntu and the laptop. The implementation is based on the pinned upstream OpenCode installation guides, existing mission queue, and durable checkpoint/approval patterns in LangGraph. Existing n8n and trading interfaces remain independent.

## Full upstream package build paths

Two additional package runtimes use the original upstream locked dependencies and
source tree instead of isolated wrapper calculations:
- Understand Anything: pinned pnpm workspace, core and skill compilation,
  dashboard and viewer build, core tests, MCP discovery.
- Trading Skills: Python 3.13, uv.lock, actual installed package, offline
  Black-Scholes fixture, MCP discovery and get_version call.

The second requires a reviewed local uv base image. Official uv documentation
lists ghcr.io/astral-sh/uv:python3.13-trixie-slim. Pull only after reviewing
the upstream image and its digest. The review pins the exact local image ID.

    python3 lab/package_runtime.py review understand-anything
    python3 lab/package_runtime.py review trading-skills
    # After explicit review and approval, for each:
    python3 lab/package_runtime.py install understand-anything --approve REVIEWED_DIGEST
    python3 lab/package_runtime.py install trading-skills --approve REVIEWED_DIGEST
    python3 lab/package_runtime.py status

These are real Docker image builds and can use substantial RAM/disk; run them
on an isolated trusted build host with sufficient capacity, not while production
jobs are running. Dependency installation explicitly permits network access;
Python package build backends may execute during dependency installation.
Review upstream lockfiles, licenses, build instructions and network policy before
approval. Build scripts receive no credentials, secrets or host source mounts.
The runtime qualification container has no network, no host mounts, no Docker
socket and a read-only root. No existing receipts or runtime images are removed.
The build uses a versioned image tag and reports only after successful probes.
MCP discovery is not proof of all tools' correctness; live trading providers,
LLM graph ingestion and dashboard access remain separate integrations.

References:
- https://github.com/egonex-ai/understand-anything/blob/b232f356446295e4eaa05b9b285e08ce5cd5e8a0/understand-anything-plugin/packages/mcp/README.md
- https://github.com/staskh/trading_skills/blob/b025c283f16d6c49344d00e384b4b0cc347546da/pyproject.toml
- https://docs.astral.sh/uv/guides/integration/docker/

Master-generated missions narrow delegated program permissions to the intersection of the reviewed plan's selected programs and the agent's own permissions. Current permissions are rechecked at each call. Capabilities provides a unified searchable read-only explorer; Diagnostics remains a separate Tools category. Planning history and cancellation use the existing task queue. General inbound MCP execution, arbitrary native model dispatch, distributed workers and other upstream package builds remain open, not qualified by this release.
