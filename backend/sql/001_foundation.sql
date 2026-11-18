CREATE TABLE users (
 id UUID PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
 enabled BOOLEAN NOT NULL DEFAULT true, failed_attempts INTEGER NOT NULL DEFAULT 0,
 locked_until TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE sessions (
 token_hash TEXT PRIMARY KEY, user_id UUID NOT NULL REFERENCES users(id),
 csrf TEXT NOT NULL, expires_at TIMESTAMPTZ NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE projects (
 id UUID PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE agents (
 id UUID PRIMARY KEY, name TEXT NOT NULL, instructions TEXT NOT NULL,
 version INTEGER NOT NULL DEFAULT 1, enabled BOOLEAN NOT NULL DEFAULT true,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE settings (key TEXT PRIMARY KEY, value JSONB NOT NULL);
CREATE TABLE documents (
 id UUID PRIMARY KEY, project_id UUID NOT NULL REFERENCES projects(id),
 title TEXT NOT NULL, content TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE runs (
 id UUID PRIMARY KEY, project_id UUID NOT NULL REFERENCES projects(id), agent_id UUID NOT NULL REFERENCES agents(id),
 agent_version INTEGER NOT NULL, instructions TEXT NOT NULL, prompt TEXT NOT NULL, model TEXT NOT NULL,
 status TEXT NOT NULL CHECK (status IN ('QUEUED','RUNNING','CANCEL_REQUESTED','CANCELLED','SUCCEEDED','FAILED')),
 requested_by UUID NOT NULL REFERENCES users(id), output TEXT, error TEXT,
 lease_until TIMESTAMPTZ, started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX runs_queue ON runs(created_at) WHERE status='QUEUED';
CREATE TABLE events (
 id BIGSERIAL PRIMARY KEY, run_id UUID REFERENCES runs(id), actor TEXT NOT NULL,
 action TEXT NOT NULL, detail JSONB NOT NULL DEFAULT '{}', created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX events_run ON events(run_id, id);
CREATE TABLE worker_status (id TEXT PRIMARY KEY, heartbeat TIMESTAMPTZ NOT NULL DEFAULT now());
