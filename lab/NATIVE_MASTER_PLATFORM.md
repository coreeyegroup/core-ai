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
