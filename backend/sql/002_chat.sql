CREATE TABLE conversations (
 id UUID PRIMARY KEY, user_id UUID NOT NULL REFERENCES users(id),
 title TEXT NOT NULL DEFAULT 'New chat', model TEXT NOT NULL,
 mode TEXT NOT NULL DEFAULT 'general' CHECK (mode IN ('general','professional')),
 instructions TEXT NOT NULL DEFAULT '', project_id UUID REFERENCES projects(id),
 temperature DOUBLE PRECISION NOT NULL DEFAULT 0.4, max_tokens INTEGER NOT NULL DEFAULT 2048,
 pinned BOOLEAN NOT NULL DEFAULT false, archived BOOLEAN NOT NULL DEFAULT false,
 forked_from UUID REFERENCES conversations(id) ON DELETE SET NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX conversations_owner ON conversations(user_id,pinned DESC,updated_at DESC);
CREATE TABLE chat_messages (
 id UUID PRIMARY KEY, conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
 sequence BIGINT GENERATED ALWAYS AS IDENTITY,
 role TEXT NOT NULL CHECK (role IN ('user','assistant')),
 content TEXT NOT NULL DEFAULT '', attachments JSONB NOT NULL DEFAULT '[]', model TEXT,
 status TEXT NOT NULL DEFAULT 'COMPLETE' CHECK (status IN ('COMPLETE','QUEUED','RUNNING','CANCEL_REQUESTED','CANCELLED','FAILED')),
 error TEXT, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX chat_messages_thread ON chat_messages(conversation_id,sequence);
CREATE TABLE chat_generations (
 id UUID PRIMARY KEY, conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
 user_message_id UUID NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
 assistant_message_id UUID NOT NULL REFERENCES chat_messages(id) ON DELETE CASCADE,
 requested_by UUID NOT NULL REFERENCES users(id), request_id UUID NOT NULL UNIQUE, request_digest TEXT NOT NULL,
 model TEXT NOT NULL, mode TEXT NOT NULL, instructions TEXT NOT NULL, project_id UUID REFERENCES projects(id),
 temperature DOUBLE PRECISION NOT NULL, max_tokens INTEGER NOT NULL,
 status TEXT NOT NULL CHECK (status IN ('QUEUED','RUNNING','CANCEL_REQUESTED','CANCELLED','SUCCEEDED','FAILED')),
 lease_until TIMESTAMPTZ, error TEXT, started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX one_active_chat_reply ON chat_generations(conversation_id) WHERE status IN ('QUEUED','RUNNING','CANCEL_REQUESTED');
CREATE INDEX chat_generation_queue ON chat_generations(created_at) WHERE status='QUEUED';
