# Offline research and engineering recipes

Four new reviewed capabilities reuse python:3.12-slim. Source pins are in
repositories.json. Last30Days, Understand Anything and Diagram Design have
MIT licenses; ML4T Skills is Apache-2.0. These are partial source-based
installations, not full native plugin installations. No new runtime image
is needed on the current host.

Use the existing batch manager on a dedicated test host. Review sources
and the exact plan before approval. The offline containers do not receive
browser cookies, API keys, production files, or network access.

    python3 -m unittest discover -s tests -p 'test_independent*.py' -v
    python3 lab/batch_install.py review
    python3 lab/batch_install.py install --approve REVIEWED_DIGEST
    python3 lab/batch_install.py status

Examples after qualification:

    IMAGE=$(docker image inspect --format '{{.Id}}' python:3.12-slim)
    python3 lab/research_programs.py run research-mock --image "$IMAGE" --params '["agent workflows"]'
    python3 lab/research_programs.py run knowledge-graph-merge --image "$IMAGE" --params-file /path/to/graph-batches.json
    python3 lab/research_programs.py run diagram-prism --image "$IMAGE" --params '[80,40,30,5]'
    python3 lab/research_programs.py run ml4t-chapter-map --image "$IMAGE" --params '[]'

- research-mock calls the original Last30Days CLI in mock mode with JSON
  output and validates its report schema. Output is explicitly labeled
  fixture data, not fresh findings. Live research requires a separate
  approved provider setup and a network policy.
- knowledge-graph-merge calls the original graph merge function. Input
  is an array of batch objects containing nodes and edges, with at most
  500 combined entries. It reports deduplication/normalization and
  unresolved issues. This is not an entire repository analysis or
  semantic graph certification. Inspect the review report before reuse.
- diagram-prism returns actual upstream dimetric geometry/path data
  for width, depth, height, and corner radius. It does not render a
  completed diagram, install browser dependencies, or create an SVG file.
- ml4t-chapter-map invokes the upstream read-only generator. It is not
  installation of the separate ML4T financial libraries.

JSON inputs have a 36,000 serialized-character limit and are passed as
arguments. Do not include credentials or confidential source code.
Output streams to the terminal; receipts and execution metadata remain
under the independent lab. No production service restarts.

## Native host gap

The pinned Superpowers .opencode/INSTALL.md describes OpenCode V1 and
V2 (>=2.0.4) plugin mechanisms. For a full installation the host version,
plugin dependency resolution, model access and plugin registration must
be tested separately in an isolated profile. Do not delete or overwrite
existing OpenCode configurations. The Understand Anything TypeScript
core/dashboard/MCP packages, Wshobson adapters, full Staskh/ML4T
packages, and the remaining native hosts are not qualified by these
four recipes. The source-only and partial-coverage statuses must stay
distinct.
