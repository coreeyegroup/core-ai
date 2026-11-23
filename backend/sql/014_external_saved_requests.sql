ALTER TABLE external_api_connections
    ADD COLUMN requests JSONB NOT NULL DEFAULT '[]'::jsonb;
