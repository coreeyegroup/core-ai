CREATE TABLE external_api_connections (
    id UUID PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    provider VARCHAR(30) NOT NULL,
    endpoint VARCHAR(2048) NOT NULL,
    method VARCHAR(8) NOT NULL,
    auth VARCHAR(16) NOT NULL,
    header_name VARCHAR(64) NOT NULL DEFAULT '',
    secret BYTEA,
    paused BOOLEAN NOT NULL DEFAULT false,
    version INTEGER NOT NULL DEFAULT 1,
    created_by UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_started_at TIMESTAMPTZ
);

CREATE TABLE external_api_activity (
    id BIGSERIAL PRIMARY KEY,
    connection_id UUID NOT NULL REFERENCES external_api_connections(id) ON DELETE CASCADE,
    occasion VARCHAR(10) NOT NULL,
    outcome VARCHAR(32) NOT NULL,
    upstream_status INTEGER,
    elapsed_ms INTEGER NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX external_api_activity_recent ON external_api_activity(connection_id, id DESC);
