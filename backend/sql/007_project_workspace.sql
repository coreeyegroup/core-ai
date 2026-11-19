ALTER TABLE projects
 ADD COLUMN default_model TEXT,
 ADD COLUMN default_mode TEXT,
 ADD COLUMN archived_at TIMESTAMPTZ;

CREATE INDEX events_chat_source_generation ON events ((detail->>'generation_id')) WHERE action='chat.sources';
