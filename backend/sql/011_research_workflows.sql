ALTER TABLE runs DROP CONSTRAINT runs_status_check;
ALTER TABLE runs ADD CONSTRAINT runs_status_check CHECK (
    status IN ('QUEUED','RUNNING','CANCEL_REQUESTED','CANCELLED','SUCCEEDED','FAILED','WAITING_REVIEW','PAUSED','SCHEDULED')
);
ALTER TABLE runs ADD COLUMN claim_token UUID;

CREATE TABLE research_workflows (
    run_id UUID PRIMARY KEY REFERENCES runs(id) ON DELETE CASCADE,
    version INTEGER NOT NULL DEFAULT 1,
    specification JSONB NOT NULL,
    phase TEXT NOT NULL DEFAULT 'PLAN' CHECK (phase IN ('PLAN','COLLECT','SYNTHESIZE','COMPLETE')),
    plan JSONB,
    evidence JSONB,
    draft TEXT,
    review_digest TEXT,
    review_expires_at TIMESTAMPTZ,
    artifact_id UUID REFERENCES workspace_artifacts(id) ON DELETE SET NULL,
    calls INTEGER NOT NULL DEFAULT 0,
    measured_input_tokens BIGINT NOT NULL DEFAULT 0,
    measured_output_tokens BIGINT NOT NULL DEFAULT 0,
    scheduled_for TIMESTAMPTZ,
    deadline TIMESTAMPTZ NOT NULL
);
CREATE INDEX research_deadline ON research_workflows(deadline) WHERE phase <> 'COMPLETE';
CREATE INDEX research_schedule ON research_workflows(scheduled_for) WHERE phase = 'PLAN';
