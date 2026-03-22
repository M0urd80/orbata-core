-- Outbound delivery registry: worker loads active rows by ``service`` (channel name), ordered by ``priority``.

CREATE TABLE IF NOT EXISTS email_delivery_providers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(128) NOT NULL,
    service VARCHAR(64) NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT true,
    provider_kind VARCHAR(64) NOT NULL DEFAULT 'smtp',
    config JSONB NULL
);

CREATE INDEX IF NOT EXISTS ix_email_delivery_providers_service
    ON email_delivery_providers (service);

CREATE INDEX IF NOT EXISTS ix_email_delivery_providers_service_active_priority
    ON email_delivery_providers (service, is_active, priority);
