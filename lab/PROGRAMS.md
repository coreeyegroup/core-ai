# Independent program recipes

The first recipe qualifies the original UI/UX Pro Max design-system engine
at its pinned source commit. Its search engine documents Python 3 with no
additional Python dependencies. This is a source-based, container-backed
installation: the managed checkout is the persistent source, the local Docker
image is the runtime, and a local qualification receipt records the exact
pair. It does not need CORE-AI, Ollama, or a database.

Use a dedicated test host or VM for executing third-party code. Docker
alone is not a complete security boundary. Review pinned source and license
before executing. Use a trusted locally available Python 3 image (for example,
the official python:3.12-slim image, pulled separately by the operator).
The runner never pulls an image or installs packages implicitly.

```sh
python3 lab/programs.py list
IMAGE=$(docker image inspect --format '{{.Id}}' python:3.12-slim)
python3 lab/programs.py review ui-ux-pro-max --image "$IMAGE"
```

Review the exact plan and copy its printed digest to the following command
instead of APPROVAL_DIGEST. It runs the real upstream script and checks that
its JSON includes nonempty colors, typography, style and pattern sections.
A receipt is created only on a successful exit; output quality still needs
human review.

```sh
python3 lab/programs.py install ui-ux-pro-max --image "$IMAGE" --approve APPROVAL_DIGEST
python3 lab/programs.py run ui-ux-pro-max --image "$IMAGE" --query "institutional trading dashboard" --project "COREI-OS-MINI"
```

The source and runtime are retained independently, while each execution's
scratch files are ephemeral. Receipts are stored under packages/RECIPE/COMMIT/
and execution results under reports/. No existing recipe receipts are
overwritten, and different image IDs can be qualified separately. If the
image tag changes, the new image ID must be independently qualified.
The existing generic review-plan/run-plan interface remains available for
other approved commands. This first recipe does not claim to install
the repository's other skills, Node CLI, host plugins, or external services.
Additional recipes and host-specific dependency installation are pending.

Tests: `python3 -m unittest discover -s tests -p 'test_independent*.py' -v`.
