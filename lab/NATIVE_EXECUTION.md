# Native model execution

The standard CORE-AI worker stays unchanged. Native Superpowers, Ponytail and combined profiles are optional Tools-mode agent capabilities, not mandatory dependencies. They execute in fresh OpenCode containers without host workspace, Docker socket, credentials or external network. A temporary Unix socket bridges only the administrator-approved local Ollama model's inventory, show and chat-completions routes. Source/image/model digest and exact mode are rechecked before every call. No package is fetched during execution.

## Operator qualification

Use the same private IPv4 endpoint and model name already configured in CORE-AI Models. The model must be locally installed, advertise completion and tools, and not be an Ollama cloud model. Run on the Ubuntu lab owner account during an idle model window. Example (substitute actual configured values):

    python3 lab/native_execution.py review superpowers --endpoint http://10.8.0.2:11434 --model qwen3:4b
    python3 lab/native_execution.py qualify superpowers --endpoint http://10.8.0.2:11434 --model qwen3:4b --approve REVIEWED_DIGEST

Repeat for ponytail and combined; default mode is full. Ponytail and combined also accept --mode lite or --mode ultra, on both review and qualify. Each model/mode needs its own qualification. Standard execution is the off alternative. A registration receipt alone is not model qualification. Superpowers requires an observed completed brainstorming skill tool call; Ponytail requires the upstream mode marker in the actual system message forwarded to Ollama, and combined requires both. A failed or timed-out fixture is not a qualification. No raw prompts or model responses are stored in qualification receipts.

    python3 lab/native_execution.py status

After qualification, deploy through the existing lab/install-integration.sh --approve-deploy workflow (review first), with both checkouts on the same release. The Tools catalog shows native model qualification records separately from registration. Agent settings and Agent Team Builder expose native.superpowers, native.ponytail and native.combined. Select Tools mode, an exact qualified local model, and one or more explicit native capabilities. In a project task ask the agent to delegate a bounded design/review problem to the permitted native tool, mode full unless another mode was qualified. Check task step history for native-opencode provenance, model calls, skill evidence, and qualification ID. Use the same agent in manual or reviewed master-planned missions. The master planner itself stays analysis-only. Native delegation from external connection tasks or Chat is not enabled by this release. No automatic deployment, repository edits, or host file access.

Native execution is bounded by the isolated 180-second run and 16 model calls, 2 GiB container memory, and existing shared gateway slot. Parent cancellation is reconciled after the bounded native call returns; no guarantee that Ollama stops immediately. A nested native run may require more time than a basic task; choose an adequate task budget. Native tools are unavailable if no current matching receipt is found. A recorded receipt is historical evidence, not a live health check. This implementation must still be qualified against the actual server's OpenCode/Ollama and user-selected model; CI fixtures do not establish real inference or autonomous workflows.
