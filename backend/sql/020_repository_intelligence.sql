ALTER TABLE skill_releases ADD COLUMN repository_inventory JSONB;

CREATE TABLE repository_assessments (
    id UUID PRIMARY KEY,
    collection_id UUID NOT NULL,
    commit_sha TEXT NOT NULL,
    created_by UUID NOT NULL REFERENCES users(id),
    model TEXT NOT NULL,
    focus TEXT NOT NULL,
    evidence_paths JSONB NOT NULL,
    report JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    FOREIGN KEY (collection_id, commit_sha) REFERENCES skill_releases(collection_id, commit_sha)
);
CREATE INDEX repository_assessments_release ON repository_assessments(collection_id, commit_sha, created_at DESC);

CREATE TABLE repository_verifications (
    id UUID PRIMARY KEY,
    assessment_id UUID NOT NULL REFERENCES repository_assessments(id),
    capability_index INTEGER NOT NULL CHECK (capability_index >= 0),
    state TEXT NOT NULL CHECK (state IN ('Verified', 'Failed', 'Untested')),
    evidence TEXT NOT NULL,
    checked_by UUID NOT NULL REFERENCES users(id),
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX repository_verifications_assessment ON repository_verifications(assessment_id, capability_index, checked_at DESC);
