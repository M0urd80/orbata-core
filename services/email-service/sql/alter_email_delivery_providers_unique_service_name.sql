-- Enforce unique provider name per service (plug-and-play registry).

ALTER TABLE email_delivery_providers
    DROP CONSTRAINT IF EXISTS uq_email_delivery_providers_service_name;

ALTER TABLE email_delivery_providers
    ADD CONSTRAINT uq_email_delivery_providers_service_name UNIQUE (service, name);
