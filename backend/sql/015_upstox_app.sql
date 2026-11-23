ALTER TABLE external_api_connections ADD COLUMN upstox_app BYTEA;

CREATE TABLE broker_analysis_tasks (
    run_id UUID PRIMARY KEY REFERENCES runs(id),
    connection_id UUID NOT NULL REFERENCES external_api_connections(id),
    connection_version INTEGER NOT NULL,
    instruments TEXT[] NOT NULL
);
CREATE TABLE broker_order_submissions (
    run_id UUID NOT NULL REFERENCES broker_analysis_tasks(run_id),
    instrument TEXT NOT NULL,
    submitted_by UUID NOT NULL REFERENCES users(id),
    payload JSONB NOT NULL,
    status TEXT NOT NULL,
    broker_order_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, instrument)
);
ALTER TABLE broker_analysis_tasks
    ADD COLUMN specialists UUID[] NOT NULL DEFAULT '{}',
    ADD COLUMN lead_agent UUID REFERENCES agents(id),
    ADD COLUMN synthesis_id UUID UNIQUE REFERENCES runs(id);
