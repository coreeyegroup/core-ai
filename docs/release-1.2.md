# CORE-AI 1.2 — adopted workspace specification

CORE-AI remains an independent product. No other CORE product, third-party dashboard, hosted VPN control plane or paid model account is required. Existing accounts, chats, project records, model endpoint and WireGuard enrollment are preserved by the forward migration.

## 1.2.1 professional chat controls

- Settings lets you choose the default response style, temperature and maximum reply tokens for new chats. The defaults are saved in your browser. Existing conversations keep their own settings.
- Professional mode offers editable starters for decision briefs, document review, technical review and research planning. Selecting one adds text to the composer for review before sending.
- The composer’s context button opens project, agent profile and response options. Starting a general chat clears the previous chat’s project and agent selections.

## Implemented increment

- One grouped navigation sidebar for conversations and operational modules; keyboard commands, collapsible groups, tabs, splits and inspect panes remain available. Consolidated typography, spacing, colors and responsive controls replace overlapping style layers. Interface and reading sizes are independent.
- Private chat with persisted incremental replies, history/search/archive/pin/export, stop/retry/edit branches, project and agent-profile instructions, in-session drafts, math and safe Markdown rendering. Agent profiles in Chat supply instructions; bounded tool execution is in Tasks.
- Files: authenticated multipart upload, processing states, SHA-256 identity, original download, extracted preview, attachment selection and project source creation. UTF-8 text/code, text-bearing PDF, DOCX and XLSX are supported. Scanned PDF/OCR, images and audio are explicitly unavailable. Uploads are limited to 10 MB, 500 MB per user and 20 queued files. Extracted text is capped at 200,000 characters; chat excerpts have tighter context limits. Spreadsheet formula results depend on cached values; macros are not executed.
- Project description/instructions, owner/editor/viewer membership, source enable/disable, immutable source versions and conflict-aware edits. Retrieval is PostgreSQL full-text keyword search; semantic/vector retrieval remains planned.
- First-class Markdown/text/code/JSON artifacts: private or project visibility, source/preview editor, revision history, comparisons, export and optimistic concurrency. Executable previews are disabled. Restoring a revision creates a new version.
- ADMIN/EDITOR/VIEWER accounts and server-enforced project access. Changes revoke sessions. No self-signup, public links or SSO. Owners control project membership; account administrators control roles.
- Model-directed task execution with the explicitly enabled tools `project.inspect`, `knowledge.search`, `artifact.create`. Provider must report tool support. Typed argument validation, current actor/project authorization, six-model-step/eight-tool-call limits, cancellation checks, 300-second budget and durable execution records. No arbitrary shell, code execution, browser or external product actions.
- Provider-reported capability/license/context inspection and observed task/chat timing/token metrics. Missing measurements remain absent; no performance estimates are presented as observations.
- Git-managed native installation/update, checksummed schema migration, dedicated PostgreSQL cluster, unprivileged API/worker and Caddy route. `verify-backup` creates a fresh snapshot, restores into a temporary database, queries it as the application role, then removes the temporary database. It does not replace live data.

## Qualification and remaining work

This is a tested product increment, not an enterprise certification or a claim that the full roadmap is complete. CI exercises actual PostgreSQL migrations, permissions, revisions and the native Ubuntu install/worker path using a deterministic CI-only model provider. Browser QA uses explicitly fictional data. Actual laptop inference, latency, uptime, public HTTPS and backup storage must be checked on the operator's server.

Next phases remain visible in the capability register: restricted coding sandbox/repository workspace; scheduled workflows and approvals; scoped integration credentials and product adapters; semantic retrieval; OCR/vision/audio; SSO/MFA and broader institutional governance; external backup retention and a complete operator-approved disaster-recovery procedure. Every feature requires its own persistence, permission, failure and recovery checks before being enabled.

## Apply

```bash
cd ~/core-ai
./core-ai update
./core-ai doctor
./core-ai test-model
./core-ai verify-backup
```

For the existing deployment, do not rerun Windows enrollment or change the model host. Updates preserve the administrator credentials; `set-login` remains an explicit local operation.

## Dependency review

Production dependencies pin jsdiff 8.0.4 and KaTeX 0.19.1; the KaTeX override also updates the math plugins’ transitive copies. Production npm audit is checked separately. The Vite 8.3.8 development toolchain currently depends on picomatch 4.0.7, for which the registry reports GHSA-fc5q-39xc-vjpf and no released patched version. This dependency is used for developer/build globs; it is not shipped as a server dependency or exposed as a production glob API. Vite binds only to loopback during development, builds use controlled repository patterns, and Caddy serves compiled static assets in production. Do not expose the development server or accept untrusted build configuration. Track the upstream fix rather than forcing an unrelated major downgrade.
