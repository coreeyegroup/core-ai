-- Preserve existing explicit broad program permission. New profiles default to no recipe access.
ALTER TABLE agents ADD COLUMN program_scope jsonb NOT NULL DEFAULT '["*"]';
ALTER TABLE agents ALTER COLUMN program_scope SET DEFAULT '[]';
ALTER TABLE runs ADD COLUMN program_scope jsonb NOT NULL DEFAULT '["*"]';
ALTER TABLE runs ALTER COLUMN program_scope SET DEFAULT '[]';
ALTER TABLE chat_generations ADD COLUMN program_scope jsonb NOT NULL DEFAULT '["*"]';
ALTER TABLE chat_generations ALTER COLUMN program_scope SET DEFAULT '[]';

CREATE TABLE program_jobs (
 id uuid PRIMARY KEY, owner_id uuid NOT NULL REFERENCES users(id),
 project_id uuid REFERENCES projects(id), parent_run uuid REFERENCES runs(id) ON DELETE CASCADE,
 parent_chat uuid REFERENCES chat_generations(id) ON DELETE CASCADE,
 recipe text NOT NULL, request_id uuid NOT NULL, input_digest text NOT NULL,
 input_data jsonb NOT NULL, expected_commit text NOT NULL, expected_image text NOT NULL,
 status text NOT NULL CHECK(status IN ('QUEUED','RUNNING','CANCEL_REQUESTED','CANCELLED','FAILED','SUCCEEDED')),
 claim_token uuid, lease_until timestamptz, started_at timestamptz, finished_at timestamptz,
 created_at timestamptz NOT NULL DEFAULT now(), retry_of uuid REFERENCES program_jobs(id),
 result jsonb, file_name text, file_data bytea, error_code text, error text,
 UNIQUE(owner_id,request_id), CHECK(parent_run IS NULL OR parent_chat IS NULL)
);
CREATE INDEX program_job_queue ON program_jobs(created_at,id) WHERE status='QUEUED';
CREATE INDEX program_job_owner ON program_jobs(owner_id,created_at DESC);

CREATE TABLE mission_templates (
 id uuid PRIMARY KEY, owner_id uuid NOT NULL REFERENCES users(id),
 project_id uuid NOT NULL REFERENCES projects(id), title text NOT NULL,
 objective text NOT NULL, steps jsonb NOT NULL, version integer NOT NULL DEFAULT 1,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE mission_runs (
 id uuid PRIMARY KEY, template_id uuid NOT NULL REFERENCES mission_templates(id),
 owner_id uuid NOT NULL REFERENCES users(id), project_id uuid NOT NULL REFERENCES projects(id),
 version integer NOT NULL, title text NOT NULL, objective text NOT NULL, steps jsonb NOT NULL,
 status text NOT NULL CHECK(status IN ('QUEUED','RUNNING','PAUSE_REQUESTED','PAUSED','CANCEL_REQUESTED','CANCELLED','FAILED','SUCCEEDED')),
 cursor integer NOT NULL DEFAULT 0, child_kind text, child_id uuid,
 history jsonb NOT NULL DEFAULT '[]', error text,
 created_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz
);
CREATE INDEX mission_run_queue ON mission_runs(created_at,id) WHERE status IN ('QUEUED','RUNNING','PAUSE_REQUESTED','CANCEL_REQUESTED');

ALTER TABLE automation_connections ADD COLUMN program_scope jsonb NOT NULL DEFAULT '[]';
ALTER TABLE program_jobs ADD COLUMN connection_id uuid REFERENCES automation_connections(id);
CREATE INDEX program_job_connection ON program_jobs(connection_id,created_at DESC) WHERE connection_id IS NOT NULL;
CREATE TABLE agent_factory_records (
 id uuid PRIMARY KEY, owner_id uuid NOT NULL REFERENCES users(id), project_id uuid NOT NULL REFERENCES projects(id),
 source_run uuid NOT NULL REFERENCES runs(id), digest text NOT NULL, draft jsonb NOT NULL,
 agent_id uuid REFERENCES agents(id), created_at timestamptz NOT NULL DEFAULT now(),
 published_at timestamptz, qualification_run uuid REFERENCES runs(id),
 qualification_version integer, reviewer_notes text, qualified_at timestamptz,
 UNIQUE(owner_id,source_run)
);
