-- TEMPORARY: failing Twilio row (invalid creds) with highest priority for service ``whatsapp``.
-- Worker tries this first → fails → fails over to real provider (e.g. ``twilio-whatsapp``).
-- Remove after testing: run ``remove_whatsapp_failover_test_provider.sql``.

INSERT INTO email_delivery_providers (
    id,
    name,
    service,
    priority,
    is_active,
    provider_kind,
    config
)
SELECT
    gen_random_uuid(),
    'failover-test',
    'whatsapp',
    -1, -- lower than e.g. ``twilio-whatsapp`` at 0 → runs first
    true,
    'twilio',
    '{"account_sid":"INVALID","auth_token":"INVALID","from_number":"whatsapp:+14155238886"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM email_delivery_providers WHERE name = 'failover-test'
);
