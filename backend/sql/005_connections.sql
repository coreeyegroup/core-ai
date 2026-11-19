CREATE TABLE automation_connections (
 id UUID PRIMARY KEY,
 name TEXT NOT NULL,
 token_hash TEXT NOT NULL UNIQUE,
 project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
 agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
 model TEXT NOT NULL,
 created_by UUID NOT NULL REFERENCES users(id),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 revoked_at TIMESTAMPTZ
);

ALTER TABLE runs ADD COLUMN connection_id UUID REFERENCES automation_connections(id) ON DELETE SET NULL;
ALTER TABLE runs ADD COLUMN request_id TEXT;
CREATE UNIQUE INDEX runs_connection_request ON runs(connection_id, request_id) WHERE connection_id IS NOT NULL;
