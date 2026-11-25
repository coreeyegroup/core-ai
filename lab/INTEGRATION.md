# Consolidated capability integration

This release connects the independent lab to CORE-AI, using the existing
Tools page and Agents/Tasks workflow. It preserves standalone use and
adds a backward-compatible migration for opt-in chat tool permission snapshots and execution history. Apply it only through the normal approved deployment. Programs are discovered from the
reviewed recipe catalog and matching qualification receipts; no arbitrary
shell or installer endpoint is exposed. Input schema validation remains
in each original wrapper. The gateway has a single execution slot and
bounded request, output, time, CPU and memory limits.

Design references: MCP tool discovery/call and JSON input schemas
(https://ts.sdk.modelcontextprotocol.io/v2/get-started/first-client),
OpenCode project/global configuration and client/server API
(https://opencode.ai/docs/config, https://opencode.ai/docs/api), and
n8n execution isolation/queue concepts
(https://docs.n8n.io/hosting/scaling/queue-mode/).
The private local socket is not itself MCP; a future adapter can expose
the same catalog without changing the recipes.

## Install on core-node (explicit operator approval)

For the existing core-node host, pull the same reviewed main release in both checkouts and use one operator-approved command:

    bash lab/install-integration.sh --approve-deploy

The command checks all receipts, installs/restarts only the independent gateway, runs an actual qualified position-sizing fixture as the application account, and then invokes the existing workstation installer (including its backup and migration process). If a gate fails, it stops; no automatic retry or unrelated cleanup.

The service unit is for the existing coreeye lab owner and core-ai
application group. Docker group access is privileged; the application
account must NOT be added to it. Prefer a dedicated test VM/rootless
runner for hostile third-party code. Container isolation is not a
strong multi-tenant security boundary. The service is optional; CORE-AI
retains its normal behavior when it is offline. Stop if paths or users
differ; adapt the unit through version control, not by editing production
code. Do not overwrite an existing unrelated service unit.

    cd ~/core-ai-lab/manager
    python3 -m unittest discover -s tests -p 'test_independent*.py' -v
    python3 lab/gateway.py --catalog
    command -v prlimit
    getent group core-ai
    getent group docker
    sudo systemd-analyze verify deploy/core-ai-lab-gateway.service
    if [ ! -e /etc/systemd/system/core-ai-lab-gateway.service ]; then
      sudo install -m 0644 deploy/core-ai-lab-gateway.service /etc/systemd/system/core-ai-lab-gateway.service
    else
      sudo cmp deploy/core-ai-lab-gateway.service /etc/systemd/system/core-ai-lab-gateway.service
    fi
    sudo systemctl daemon-reload
    sudo systemctl enable --now core-ai-lab-gateway
    sudo systemctl is-active core-ai-lab-gateway
    sudo -u core-ai python3 -c 'import socket,json; s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); s.settimeout(45); s.connect("/run/core-ai-lab/gateway.sock"); s.sendall(b"{\"action\":\"catalog\"}\n"); d=json.loads(s.makefile("rb").readline()); print(d["ok"],len(d["data"]["programs"]))'

After the approved normal CORE-AI deployment, open Tools. Select an
available program, inspect its parameter example, supply data and run.
Document upload is 4 MiB; generated output up to 6 MiB, subject to the
10 MiB wire frame. Download new documents, never overwrite inputs.
Manual outputs remain in the panel until refreshed; metadata-only
execution records are in lab/reports/gateway and application events.
Do not include credentials in program inputs: numeric arguments are
transmitted as process arguments. If a result is too large, it fails or
is explicitly truncated rather than being silently treated as complete.

For agent tasks select Tools mode and explicitly enable program.list
and program.run on an existing agent. Use a tool-capable local model and
a project. Agent file inputs must be in that project and authorized by
existing file ACLs. Generated documents go into the existing project file
library subject to quota and queue limits. Notebook JSON is retained as
a .ipynb.json file; manual download uses .ipynb. Agent results are
bounded for model context. Standard conversation generation is unchanged by default. In Chat, select a Tools-mode agent with program.run permission and explicitly enable Use programs. Chat executes the bounded tool loop and shows recorded results; attached file access is limited to current-message attachments in the current project (or private files for a private chat).
No autonomous install, live research, shell, broker action or production
file access is granted. Cancellation of an in-flight offline program is
bounded by its timeout; immediate process cancellation and durable
manual run queues remain future work.

## Acceptance gates

- All existing 26 receipts remain valid and standalone commands still work.
- Gateway rejects unknown programs, extra fields, unqualified versions,
  file paths, oversize inputs and unsupported types.
- As an authenticated writer, manually run position-sizing, verify 20
  units for the qualification example, then upload a document and
  download the generated output; confirm original is unchanged.
- As VIEWER, POST execution must fail. As a permitted agent, run
  program.list then program.run using the same example; inspect steps.
- Verify offline gateway does not prevent normal chat or other modules.
- Check Chat with Use programs on and off, including permission revocation and attached-file scope.
- Review native OpenCode registration separately; package installation
  alone is not an agent qualification.

## Remaining repository work

All 24 source pins remain managed. 11 repositories have reviewed partial
program coverage (26 recipes). Other collections require native plugin,
instruction-only, provider-backed or package-specific review, not
automatic execution of every source file. The catalog shows coverage
truthfully. Remaining work includes full Understand Anything packages,
Staskh/ML4T libraries, live research providers, Wshobson, Superpowers,
Caveman, Ponytail and the other collected skill ecosystems. A complete
coverage inventory, host-specific install approval, and functionality
checks are required before declaring any entire repository installed.
