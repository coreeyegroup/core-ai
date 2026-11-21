CREATE TABLE skill_collections (
    id UUID PRIMARY KEY,
    repository TEXT NOT NULL,
    git_ref TEXT NOT NULL,
    active_commit TEXT,
    UNIQUE (repository, git_ref)
);

CREATE TABLE skill_releases (
    collection_id UUID NOT NULL REFERENCES skill_collections(id),
    commit_sha TEXT NOT NULL,
    skills JSONB NOT NULL,
    imported_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (collection_id, commit_sha)
);

ALTER TABLE skill_collections ADD FOREIGN KEY (id, active_commit)
    REFERENCES skill_releases(collection_id, commit_sha);

CREATE TABLE agent_skill_collections (
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    collection_id UUID NOT NULL REFERENCES skill_collections(id),
    PRIMARY KEY (agent_id, collection_id)
);

CREATE TABLE skill_exclusions (
    collection_id UUID NOT NULL REFERENCES skill_collections(id),
    path TEXT NOT NULL,
    PRIMARY KEY (collection_id, path)
);

ALTER TABLE runs ADD COLUMN skill_versions JSONB NOT NULL DEFAULT '[]';
ALTER TABLE runs ADD COLUMN skill_context TEXT NOT NULL DEFAULT '';
ALTER TABLE chat_generations ADD COLUMN skill_versions JSONB NOT NULL DEFAULT '[]';
ALTER TABLE chat_generations ADD COLUMN skill_context TEXT NOT NULL DEFAULT '';
