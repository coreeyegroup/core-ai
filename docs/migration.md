# Migration and recovery

The repository's active application is replaced with a custom CORE-AI workbench, FastAPI API and native worker. The old dashboard containers and Compose deployment are not part of the new application source. Git history remains available so earlier source can be reviewed.

## Existing installations

Run `git pull --ff-only origin main` then `./core-ai install`. Before infrastructure/build changes, the installer creates a root-only consistent legacy archive of `.env`, `config.env`, `runtime/`, `data/` and `data-anythingllm/` when present. Only running containers with the exact known CORE-AI names and matching Compose project label are stopped during that archive, then restarted.

The existing private WireGuard configuration is kept, including keys and laptop enrollment. No need to repeat laptop setup when the existing tunnel works. The new API uses the same private model address directly, instead of reaching it through a dashboard container.

The new login initially reuses previously configured local administrator credentials where available; it stores a scrypt hash in the new database. No previous dashboard conversation or workspace data is converted. Old private configuration remains locally for recovery and is ignored by Git. Do not upload archives, configuration files or tunnel private keys.

Old containers are stopped only after new application health, database, session protection, worker heartbeat and Caddy validation pass. Legacy containers/images/volumes are not deleted automatically. Their data is retained for deliberate later export or removal. This avoids losing unrelated private files through a broad cleanup command.

## Backups

`./core-ai backup` creates a transactionally consistent PostgreSQL custom-format dump plus the root-only environment, Caddy site and active release path under `backups/workstation-TIMESTAMP/`. Updates take the same snapshot before migrations. This is an on-host recovery copy; arrange an encrypted off-host copy for disk/server-loss recovery.

## Application/routing rollback

Each deployment retains the previous immutable release. Failures during startup, health checking, routing or enabling services restore the old unit files, running/enabled state, release pointers and Caddy configuration. Existing unrelated sites are not rewritten. Routing configuration snapshots are retained under `backups/routing-TIMESTAMP/`.

A successfully applied database migration is not automatically rolled back with application code. Future schema changes must remain compatible with the immediately previous application release or include a reviewed maintenance/restore procedure. Never blindly restore a database while workers are running.

## Database recovery procedure

Use a backup produced by this product. This operation replaces CORE-AI database contents; choose the exact backup before starting. Stop `core-ai-api` and `core-ai-worker`, validate the dump with `pg_restore --list`, restore into a temporary database owned by `core_ai_app`, run schema and row-count checks, and only then replace the live CORE-AI database during the maintenance window. Restore its matching environment if credentials were lost. The cluster administrator must not point recovery at any other product database.

This release deliberately provides backup plus documented recovery requirements; it does not expose a one-click destructive restore control. A successful backup does not by itself establish a tested restore. Perform a disposable restore drill before treating the installation as fully recovery-qualified.

## Isolated restore verification

Run `./core-ai verify-backup` after updating. It creates a fresh consistent dump, restores it into a randomly named temporary database in the dedicated CORE-AI cluster, checks schema/users/projects/artifact access as the application role, records the verification result with that backup, then drops only the temporary database. Live data and running services are retained. CI runs this drill through the native installed deployment. It verifies a current snapshot; off-host recovery and selection/replacement of a live database remain separate operator procedures.
