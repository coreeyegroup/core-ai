# Independent program lab (initial release)

Runs with Python 3.10+ and Git, independently of CORE-AI, its database and its
models. Docker is required only for explicitly approved offline test plans.
No third-party installer, hook or program runs during sync or inventory.

## Start

From the core-ai Git checkout:

```sh
python3 lab/manager.py list
python3 lab/manager.py sync nextlevelbuilder/ui-ux-pro-max-skill
python3 lab/manager.py sync all
```

The manifest pins 24 upstream HEAD commits observed on 2026-11-25. They are
not asserted to match all activated CORE-AI collection versions. Use
`--commit FULL_SHA` for a reviewed alternative, or a separate manifest.
Managed checkouts are under ~/core-ai-lab/repositories/OWNER/NAME/COMMIT.
Existing flat/nested clones are left untouched. A failed partial checkout is
preserved; inspect it before manually moving it aside. Inventory JSON is
written under reports/OWNER/NAME/COMMIT/ and classifies candidate programs,
agents, skills, hooks, manifests, documentation, licenses and other files.
Classification is heuristic, not a complete dependency or security audit.
Git submodules and LFS objects are not fetched by this command; resolve
them separately after review. No source updates occur in place.

## Standalone program qualification

Use a dedicated test VM/host, not a production host containing secrets.
Review complete pinned sources, license, dependencies and intended entry
points. Install any missing dependencies separately using reviewed
repository-specific instructions. Use a reviewed local Docker image with
the runtime/dependencies already present. The image must have /bin/sh and cp.
The offline runner is deliberately not an unrestricted shell service.

Example plan (replace image with actual local image ID from
`docker image inspect --format '{{.Id}}' IMAGE`):

```json
{
  "repo": "nextlevelbuilder/ui-ux-pro-max-skill",
  "commit": "8db36338810d0942567b97ce439affd1619fcf31",
  "image": "sha256:REPLACE_WITH_64_HEX_CHARACTERS",
  "timeout": 60,
  "steps": [
    ["python3", ".claude/skills/ui-ux-pro-max/scripts/search.py",
     "institutional financial trading dashboard", "--design-system",
     "-p", "COREI-OS-MINI"]
  ]
}
```

Save this as a new JSON file under your lab. Review then explicitly approve
the printed digest:

```sh
python3 lab/manager.py review-plan ~/core-ai-lab/uiux-plan.json
python3 lab/manager.py run-plan ~/core-ai-lab/uiux-plan.json --approve EXACT_REVIEWED_DIGEST
```

The runner copies the source into ephemeral container storage and runs the
reviewed argv steps sequentially; no network, root, added capabilities,
Docker socket or production secrets are provided. It enforces time and
resource limits, does not pull images, and records exit status. It does
not persist installed packages or automatically certify semantic output.
Inspect the output before marking a capability verified. Do not enter
secrets into plans or print them in program output. Docker is not a full
security boundary against hostile code; use dedicated VM isolation for
untrusted repositories. Networked installation, persistent environments,
host-specific plugins (Superpowers/OpenCode etc.), dependency resolution,
credential management, integration adapters and UI are follow-up work.

## Tests

```sh
python3 -m unittest discover -s tests -p test_independent_lab.py -v
```

Tests exercise a temporary Git fixture and approval/command construction;
no third-party programs are executed by tests.
