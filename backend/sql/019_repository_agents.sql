ALTER TABLE skill_releases ADD COLUMN agent_definitions JSONB;
ALTER TABLE agents ADD COLUMN imported_source JSONB;
CREATE UNIQUE INDEX agents_imported_source_unique ON agents
    (owner_id, (imported_source->>'repository'), (imported_source->>'path'))
    WHERE imported_source IS NOT NULL;
