# CORE-AI requirements and acceptance register

This register tracks the adopted product specification. Status describes implemented behavior, not an enterprise certification. The live deployment and actual laptop hardware require operator-side qualification after installation.

| Requirement | User surface | Backend / persistence | Verification | Audit status |
| --- | --- | --- | --- | --- |
| General and professional conversation | Chat / composer | Private conversations and durable generations | API, browser and native-worker checks | Implemented; unified navigation and independent reading size |
| Consistent workspace | Global sidebar, panels, commands | Versioned browser layout | Browser, keyboard and responsive checks | Implemented; one sidebar and consolidated design system |
| Conversation lifecycle | History, search, edit, stop, export | Conversation/message/generation records | Ownership, idempotency and cancellation tests | Implemented; in-session drafts and project/profile context |
| File lifecycle | Files / attach / preview | Validated parsing, file records and project source references | Format, size, ownership and extraction tests | Implemented for UTF-8 text/code, text-bearing PDF, DOCX and XLSX; OCR unavailable |
| Project knowledge | Projects / sources | Project instructions, membership and source versions | Retrieval and permission tests | Implemented: instructions, memberships, keyword search and source revisions; semantic search planned |
| Artifact lifecycle | Library / right editor | Immutable revisions with optimistic concurrency | Edit, stale-save, ownership and export tests | Implemented: first-class editable artifacts, revisions and comparisons |
| Agent execution | Agents / task timeline | Bounded typed tools, permissions, durable steps | Dispatch, budget and cancellation tests | Implemented: bounded model-directed project tools; sandbox planned |
| Model capability control | Models / composer | Provider discovery and capability reports | Capability and offline-state tests | Implemented: explicit provider-reported capability inspection and runtime tools check |
| Access control | Settings / access | Roles, project membership and revocable sessions | Permission/ownership tests | Implemented: ADMIN/EDITOR/VIEWER and project memberships; SSO planned |
| Operations | Operations / diagnostics | Audit, observed runtime metrics, backups and releases | Native deployment and recovery checks | Implemented: observed metrics and isolated snapshot restore check; disaster-recovery runbook remains planned |
| Safe code execution | Repository workspace | Separate restricted execution environment | Isolation and replay/reconciliation qualification | Planned; no host-shell control advertised |
| Workflow scheduling and connections | Capability register / Connections | Optional versioned scoped adapters | Contract and authorization tests | Planned; no configured external connections |
| Multimodal capabilities | Capability register | Model-dependent OCR/vision/audio adapters | Real processing/model qualification | Planned; no false upload claims |
| Optional product integration | Connections | Separate product APIs/data/identity | Independent-start/failure-isolation checks | No mandatory product connections; adapters planned |

## Acceptance checklist

- A new user can start a chat without creating a project or agent.
- Sidebar navigation is available at every viewport width.
- Every implemented module remains reachable through navigation and commands.
- Typography, spacing, focus states, tables and controls use one design system.
- Reading text is legible; compact interface controls do not force tiny answer text.
- Existing conversations, credentials, projects and tunnel settings survive migration.
- Files have validated formats, processing results, previews and ownership enforcement.
- Artifacts are editable records with revisions, not a label applied to plain chat output.
- Agent tool execution is bounded and recorded; source text cannot grant permissions.
- Model capabilities and unavailable controls report real reasons.
- Native installation, migration, backup and worker checks pass before release.
- Fixtures remain clearly marked and excluded from production entry points.

## Release evidence

Release 1.2 adds real PostgreSQL permission/revision/file/tool integration tests, parser-limit unit checks, UI chat/navigation/split coverage and native Ubuntu install/update smoke tests. The native test exercises a real systemd API/worker/database with a deterministic CI-only provider. This does not certify real-model response quality or VPS performance. See [release notes](release-1.2.md) for boundaries and installation checks.
