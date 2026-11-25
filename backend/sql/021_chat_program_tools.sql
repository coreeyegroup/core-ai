-- Explicit opt-in and immutable permission snapshot for each chat generation.
ALTER TABLE chat_generations ADD COLUMN program_tools jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE chat_generations ADD COLUMN program_steps jsonb NOT NULL DEFAULT '[]'::jsonb;
