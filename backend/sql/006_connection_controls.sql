ALTER TABLE automation_connections
 ALTER COLUMN project_id DROP NOT NULL,
 ALTER COLUMN agent_id DROP NOT NULL,
 ALTER COLUMN model DROP NOT NULL,
 ADD COLUMN allowed_models TEXT[],
 ADD COLUMN allow_model_choice BOOLEAN NOT NULL DEFAULT false,
 ADD COLUMN client_type TEXT NOT NULL DEFAULT 'custom',
 ADD COLUMN can_discover BOOLEAN NOT NULL DEFAULT true,
 ADD COLUMN can_submit BOOLEAN NOT NULL DEFAULT true,
 ADD COLUMN can_read BOOLEAN NOT NULL DEFAULT true,
 ADD COLUMN paused BOOLEAN NOT NULL DEFAULT false,
 ADD COLUMN expires_at TIMESTAMPTZ,
 ADD COLUMN last_used_at TIMESTAMPTZ,
 ADD COLUMN requests_per_minute INTEGER NOT NULL DEFAULT 30,
 ADD COLUMN max_pending INTEGER NOT NULL DEFAULT 20,
 ADD COLUMN timeout_seconds INTEGER NOT NULL DEFAULT 300,
 ADD COLUMN max_output_tokens INTEGER NOT NULL DEFAULT 2048;
UPDATE automation_connections SET allowed_models=ARRAY[model];
ALTER TABLE automation_connections ALTER COLUMN allowed_models SET NOT NULL;
ALTER TABLE automation_connections ADD CHECK (cardinality(allowed_models)>0 AND ((model IS NULL AND allow_model_choice) OR (model IS NOT NULL AND model=ANY(allowed_models))));
ALTER TABLE runs
 ALTER COLUMN project_id DROP NOT NULL,
 ALTER COLUMN agent_id DROP NOT NULL,
 ALTER COLUMN agent_version DROP NOT NULL,
 ADD COLUMN timeout_seconds INTEGER NOT NULL DEFAULT 300,
 ADD COLUMN max_output_tokens INTEGER NOT NULL DEFAULT 2048,
 ADD CHECK ((project_id IS NOT NULL AND agent_id IS NOT NULL)
   OR (request_id IS NOT NULL AND runtime_mode='analysis'));
CREATE INDEX runs_connection_activity ON runs(connection_id, created_at DESC) WHERE connection_id IS NOT NULL;
