-- Email channel: at least one active row so ``send_with_failover`` can route (credentials may still come from env via BrevoProvider).

INSERT INTO email_delivery_providers
    (name, service, priority, is_active, provider_kind, config)
SELECT
    'smtp-primary',
    'email',
    0,
    true,
    'smtp',
    '{}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM email_delivery_providers WHERE name = 'smtp-primary'
);
