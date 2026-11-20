ALTER TABLE automation_connections
    DROP CONSTRAINT automation_connections_check,
    ADD COLUMN model_access TEXT NOT NULL DEFAULT 'selected' CHECK (model_access IN ('selected','all')),
    ADD COLUMN model_policies JSONB NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(model_policies)='object'),
    ADD COLUMN can_embed BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN can_cancel BOOLEAN NOT NULL DEFAULT false,
    ADD COLUMN previous_token_hash TEXT UNIQUE,
    ADD COLUMN previous_valid_until TIMESTAMPTZ,
    ADD COLUMN context_tokens INTEGER NOT NULL DEFAULT 8192 CHECK (context_tokens BETWEEN 1024 AND 32768),
    ADD CONSTRAINT automation_connection_model_scope CHECK (
        (model IS NOT NULL OR allow_model_choice)
        AND (model_access='all' OR (cardinality(allowed_models)>0 AND (model IS NULL OR model=ANY(allowed_models))))
    );

ALTER TABLE runs
    ADD COLUMN operation TEXT NOT NULL DEFAULT 'generation' CHECK (operation IN ('generation','embedding')),
    ADD COLUMN context_tokens INTEGER NOT NULL DEFAULT 8192 CHECK (context_tokens BETWEEN 1024 AND 32768),
    ADD COLUMN retry_of UUID REFERENCES runs(id) ON DELETE SET NULL;
