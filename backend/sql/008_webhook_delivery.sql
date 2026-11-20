ALTER TABLE automation_connections ADD COLUMN webhook_destination TEXT;

CREATE TABLE automation_webhook_deliveries (
 run_id UUID PRIMARY KEY REFERENCES runs(id) ON DELETE CASCADE,
 destination TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','DELIVERED','FAILED','CANCELLED')),
 attempts INTEGER NOT NULL DEFAULT 0,
 next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX automation_webhook_due ON automation_webhook_deliveries(next_attempt_at) WHERE status='PENDING';
