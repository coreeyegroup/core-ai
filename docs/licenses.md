# Open-source component selection

| Component | Selected role | Upstream license / source |
|---|---|---|
| AnythingLLM 1.20.0 | Dashboard, authentication, project workspaces | [MIT](https://github.com/Mintplex-Labs/anything-llm/blob/v1.20.0/LICENSE) |
| Ollama | Existing model runtime | [MIT](https://github.com/ollama/ollama/blob/main/LICENSE) |
| WireGuard Linux / tools | Direct private tunnel | [GPL-2.0 component licenses](https://git.zx2c4.com/wireguard-tools/tree/COPYING) |
| WireGuard Windows | Private tunnel client | [MIT](https://github.com/WireGuard/wireguard-windows/blob/master/COPYING) |
| Caddy | Existing HTTPS reverse proxy | [Apache-2.0](https://github.com/caddyserver/caddy/blob/master/LICENSE) |
| Docker Engine / Moby | Container runtime | [Apache-2.0](https://github.com/moby/moby/blob/master/LICENSE) |
| Docker Compose | Deployment orchestration | [Apache-2.0](https://github.com/docker/compose/blob/main/LICENSE) |
| SQLite | Embedded application database | [Public domain](https://www.sqlite.org/copyright.html) |
| LanceDB | Embedded vector storage | [Apache-2.0](https://github.com/lancedb/lancedb/blob/main/LICENSE) |
| OpenSSH | Peer enrollment transport | [BSD-style component licenses](https://www.openssh.com/license.html) |

This is a selection record for the main components, not an exhaustive transitive-dependency SBOM or a legal opinion. Preserve upstream notices. The generated deployment code is MIT licensed in this repository.

## Excluded from the active deployment

- Hosted VPN coordination is not required: the WireGuard peers exchange public keys directly over the user's existing SSH access.
- The previous dashboard is retained only as stopped migration history/data, not as the new runtime. Open WebUI's current license adds a branding restriction.
- LibreChat was evaluated but its standard MongoDB dependency uses SSPL, which MongoDB states is not considered open source by OSI. The chosen single-container stack avoids that dependency.

## Models and platform boundaries

Each downloaded model/weight package has its own terms. The runtime license does not license the weights. Verify exact model/tag provenance and intended usage separately; no license is inferred from an Ollama model name.

The user-supplied Windows OS and any proprietary GPU drivers remain platform dependencies. This deployment does not claim to turn those components into open-source software. There is no required cloud AI account or VPN-vendor account in the inference path. Downloading packages/images, using Git hosting, and obtaining public HTTPS certificates still involve external distribution/PKI infrastructure.
