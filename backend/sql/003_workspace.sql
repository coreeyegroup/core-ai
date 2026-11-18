ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'ADMIN' CHECK(role IN ('ADMIN','EDITOR','VIEWER'));
ALTER TABLE projects ADD COLUMN owner_id UUID REFERENCES users(id);
ALTER TABLE projects ADD COLUMN instructions TEXT NOT NULL DEFAULT '';
ALTER TABLE projects ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
UPDATE projects SET owner_id=(SELECT id FROM users ORDER BY created_at LIMIT 1) WHERE owner_id IS NULL;
CREATE TABLE project_members (project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,role TEXT NOT NULL CHECK(role IN ('OWNER','EDITOR','VIEWER')),PRIMARY KEY(project_id,user_id));
INSERT INTO project_members SELECT id,owner_id,'OWNER' FROM projects WHERE owner_id IS NOT NULL;
ALTER TABLE agents ADD COLUMN owner_id UUID REFERENCES users(id);
ALTER TABLE agents ADD COLUMN runtime_mode TEXT NOT NULL DEFAULT 'analysis' CHECK(runtime_mode IN ('analysis','tools'));
ALTER TABLE agents ADD COLUMN tools JSONB NOT NULL DEFAULT '["knowledge.search","project.inspect"]';
UPDATE agents SET owner_id=(SELECT id FROM users ORDER BY created_at LIMIT 1) WHERE owner_id IS NULL;
ALTER TABLE runs ADD COLUMN runtime_mode TEXT NOT NULL DEFAULT 'analysis';
ALTER TABLE runs ADD COLUMN tools JSONB NOT NULL DEFAULT '[]';
ALTER TABLE runs ADD COLUMN metrics JSONB NOT NULL DEFAULT '{}';
ALTER TABLE documents ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE documents ADD COLUMN enabled BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE documents ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
CREATE TABLE document_versions (id BIGSERIAL PRIMARY KEY,document_id UUID REFERENCES documents(id) ON DELETE SET NULL,project_id UUID NOT NULL REFERENCES projects(id),version INTEGER NOT NULL,title TEXT NOT NULL,content TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT now());
INSERT INTO document_versions(document_id,project_id,version,title,content) SELECT id,project_id,version,title,content FROM documents;
CREATE TABLE workspace_files (
 id UUID PRIMARY KEY,owner_id UUID NOT NULL REFERENCES users(id),project_id UUID REFERENCES projects(id),
 name TEXT NOT NULL,media_type TEXT NOT NULL,size_bytes INTEGER NOT NULL,sha256 TEXT NOT NULL,raw BYTEA NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('QUEUED','PROCESSING','READY','FAILED')),text_content TEXT NOT NULL DEFAULT '',
 error TEXT,truncated BOOLEAN NOT NULL DEFAULT false,document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
 lease_until TIMESTAMPTZ,created_at TIMESTAMPTZ NOT NULL DEFAULT now(),processed_at TIMESTAMPTZ
);
CREATE INDEX workspace_files_owner ON workspace_files(owner_id,created_at DESC);
CREATE TABLE workspace_artifacts (
 id UUID PRIMARY KEY,owner_id UUID NOT NULL REFERENCES users(id),project_id UUID REFERENCES projects(id),
 title TEXT NOT NULL,kind TEXT NOT NULL CHECK(kind IN ('markdown','text','code','json')),language TEXT NOT NULL DEFAULT '',
 visibility TEXT NOT NULL DEFAULT 'PRIVATE' CHECK(visibility IN ('PRIVATE','PROJECT')),version INTEGER NOT NULL DEFAULT 1,
 source_run_id UUID REFERENCES runs(id),source_message_id UUID REFERENCES chat_messages(id) ON DELETE SET NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE artifact_versions (
 id UUID PRIMARY KEY,artifact_id UUID NOT NULL REFERENCES workspace_artifacts(id) ON DELETE CASCADE,version INTEGER NOT NULL,
 content TEXT NOT NULL,sha256 TEXT NOT NULL,actor_id UUID NOT NULL REFERENCES users(id),reason TEXT NOT NULL DEFAULT '',created_at TIMESTAMPTZ NOT NULL DEFAULT now(),UNIQUE(artifact_id,version)
);
CREATE TABLE agent_steps (
 id BIGSERIAL PRIMARY KEY,run_id UUID NOT NULL REFERENCES runs(id),step INTEGER NOT NULL,kind TEXT NOT NULL,
 tool TEXT,input JSONB NOT NULL DEFAULT '{}',result JSONB NOT NULL DEFAULT '{}',created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE conversations ADD COLUMN agent_id UUID REFERENCES agents(id);
ALTER TABLE chat_generations ADD COLUMN agent_id UUID REFERENCES agents(id);
ALTER TABLE chat_generations ADD COLUMN agent_instructions TEXT NOT NULL DEFAULT '';
ALTER TABLE chat_generations ADD COLUMN metrics JSONB NOT NULL DEFAULT '{}';
