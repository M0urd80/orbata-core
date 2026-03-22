-- Idempotent: add routing columns for existing DBs created before provider_kind/config.

ALTER TABLE email_delivery_providers
    ADD COLUMN IF NOT EXISTS provider_kind VARCHAR(64) NOT NULL DEFAULT 'smtp';

ALTER TABLE email_delivery_providers
    ADD COLUMN IF NOT EXISTS config JSONB NULL;

CREATE INDEX IF NOT EXISTS ix_email_delivery_providers_service_active_priority
    ON email_delivery_providers (service, is_active, priority);
