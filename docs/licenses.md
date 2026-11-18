# Software and model licensing

CORE-AI application source is MIT licensed. It uses open-source React, TypeScript, Vite, FastAPI, Uvicorn, HTTPX, Psycopg, PostgreSQL, Caddy and WireGuard. Consult each upstream project's license when redistributing dependencies. The Python/Node installer downloads official releases with declared checksums.

The active application does not use AnythingLLM or Open WebUI and has no hosted VPN control-plane dependency. Their previous local data/container images may remain solely for migration recovery; they are not a runtime requirement.

Workbench controls, icons and theme tokens were adapted from the user-owned `coreeyegroup/corei-os-mini` reference. Application logic and deployment resources belong to CORE-AI independently.

Ollama model weights have individual licenses. An open-source inference engine does not make every model open source or grant unrestricted commercial redistribution. Keep a model license inventory before enabling models for commercial redistribution. Windows and any proprietary GPU drivers are separate operating-environment choices, not open-source components of CORE-AI.
