-- Idempotency: skip re-sending when this row was already marked delivered.
-- Run against the same DB that holds ``email_logs`` (core-auth / shared Postgres).

ALTER TABLE email_logs
    ADD COLUMN IF NOT EXISTS delivered BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS ix_email_logs_delivered ON email_logs (delivered);
