# Independent native host: OpenCode V2 and Superpowers

This is a separate native-host probe, not part of the offline Python
batch. It does not change Claude Code, Codex, host Node, CORE-AI,
or user-wide configuration. Superpowers uses the original pinned source
directory via the V2 local directory plugin mechanism. No model call,
public port, credentials, production repository, or Docker socket is
needed for the first probe.

Official references:
- https://opencode.ai/docs/ (V2 npm package @opencode/cli)
- https://opencode.ai/docs/plugins/
- https://opencode.ai/docs/cli/plugins/
- https://github.com/obra/superpowers/blob/22f0b463e7a5e579904dd6211a520321035526f7/.opencode/INSTALL.md

## Acquisition and review

Use a dedicated test VM. Review the Dockerfile and plugin source before
running third-party install scripts. The V2 npm package has a native
binary selection postinstall. The build runs this as an unprivileged
container user, without production credentials or host bind mounts.
Choose a published stable V2 version >=2.0.4 after inspecting npm
metadata. No hardcoded claim about the latest package is made.

    npm view @opencode/cli@latest version dist.integrity scripts --json

After reviewing metadata, set OPENCODE_VERSION to that exact version.
Use an official Node 22 base and record its immutable digest:

    docker pull node:22-bookworm-slim
    NODE_BASE=$(docker image inspect --format '{{index .RepoDigests 0}}' node:22-bookworm-slim)
    printf '%s\n' "$NODE_BASE"
    docker build --build-arg NODE_BASE="$NODE_BASE" --build-arg OPENCODE_VERSION="$OPENCODE_VERSION" -t core-ai-lab-opencode:0.1.0 lab/runtime/opencode

The Docker image retains npm's generated lockfile; base and direct
package versions are fixed for a given build. Transitive resolution
is not independently hash-locked before building. Record image ID
and review lockfile; the image is not certified free of vulnerabilities.
Do not rebuild an existing tag without operator approval; use a new
tag and pass it to the native manager if one already exists.

    python3 lab/native_host.py review
    # Copy exact displayed digest after inspecting the plan.
    python3 lab/native_host.py verify --approve REVIEWED_DIGEST

The probe runs --version and plugin list in fresh offline non-root
containers. Only the pinned plugin source is mounted read-only;
container home and workspace are temporary. It records version match
and whether the listing mentions superpowers, not a full qualification.
Inspect the actual listing for active plugin status. An absent plugin,
timeout or version mismatch must be investigated; never mark a failed
plugin as qualified. The runtime may require further dependencies or a
different supported version. No automatic provider setup is performed.

Next gate: configure an explicitly approved private Ollama endpoint,
test tool calling and load the brainstorming skill in a disposable
workspace, with no access to production files or live trading. Keep the
native runtime separate from the independent offline Python registry.
