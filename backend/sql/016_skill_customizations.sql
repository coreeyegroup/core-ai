CREATE TABLE skill_collection_edits (
    collection_id UUID NOT NULL,
    commit_sha TEXT NOT NULL,
    path TEXT NOT NULL,
    description TEXT NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (collection_id, commit_sha, path),
    FOREIGN KEY (collection_id, commit_sha) REFERENCES skill_releases(collection_id, commit_sha)
);

CREATE TABLE agent_skill_edits (
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    collection_id UUID NOT NULL,
    commit_sha TEXT NOT NULL,
    path TEXT NOT NULL,
    description TEXT NOT NULL,
    body TEXT NOT NULL,
    PRIMARY KEY (agent_id, collection_id, commit_sha, path),
    FOREIGN KEY (collection_id, commit_sha) REFERENCES skill_releases(collection_id, commit_sha)
);

CREATE TABLE agent_skill_exclusions (
    agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    collection_id UUID NOT NULL REFERENCES skill_collections(id),
    path TEXT NOT NULL,
    PRIMARY KEY (agent_id, collection_id, path)
);
