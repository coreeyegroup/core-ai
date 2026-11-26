# Agent team operating flow

The existing mission queue remains the execution engine. Workflows → Build agent team
creates one or more new agent profiles, skill collection assignments, explicitly selected
tools and program scopes, and a reusable mission in a single database transaction.
Choose a project, objective, models, task instructions and dependencies. Each task can
use automatic skill selection, exact pinned manual selections (up to 8), or no skills.
Current collection versions are checked at creation; manual skills are checked again
when launching and enqueuing the child. Automatic skills use the current assigned
collections at execution. Existing agents and assignments are unchanged. Existing mission
editor, master planner, Chat and Tasks remain available. No task is launched by setup;
launch the saved mission explicitly. Agent-driven tool calls use existing permission
intersection. A request ID makes retries idempotent while the saved mission is unedited.

A failed optional native profile or upstream package does not prevent the 38 previously
qualified programs and instruction-only skills from being used. For the first end-to-end
check use a two-agent research/reviewer mission with supplied synthetic evidence and no
external actions. Inspect child task skill provenance, result and final mission status.

Current host blockers: Docker builds cannot resolve registry.npmjs.org and
files.pythonhosted.org; all OpenCode probes returned empty registration lists and
version mismatch. Diagnose host vs Docker DNS and the actual version/API response
before changing firewall, daemon DNS, plugin loader or network policy. No production
network configuration changes are authorized by this release. Native model execution,
full package installation and live provider access remain unqualified.
