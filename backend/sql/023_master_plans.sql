CREATE TABLE master_plans (
 id uuid PRIMARY KEY, owner_id uuid NOT NULL REFERENCES users(id),
 project_id uuid NOT NULL REFERENCES projects(id),
 planner_run uuid NOT NULL UNIQUE REFERENCES runs(id),
 objective text NOT NULL, model text NOT NULL, capabilities jsonb NOT NULL,
 mission_id uuid REFERENCES mission_templates(id), approved_digest text,
 created_at timestamptz NOT NULL DEFAULT now(), approved_at timestamptz
);
CREATE INDEX master_plans_owner ON master_plans(owner_id,created_at DESC);
ALTER TABLE mission_templates ADD COLUMN reviewed_capabilities jsonb;
