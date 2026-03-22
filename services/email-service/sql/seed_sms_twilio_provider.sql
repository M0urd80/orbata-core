-- DB-driven SMS: Twilio row with required ``from_number`` in config (no TWILIO_PHONE_NUMBER fallback).

INSERT INTO email_delivery_providers
    (name, service, priority, is_active, provider_kind, config)
SELECT
    'twilio-sms',
    'sms',
    0,
    true,
    'twilio',
    '{"from_number": "+12764962081"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM email_delivery_providers WHERE name = 'twilio-sms'
);

-- Optional: log-only failover (no Twilio creds required).
INSERT INTO email_delivery_providers
    (name, service, priority, is_active, provider_kind, config)
SELECT 'dummy-backup', 'sms', 10, true, 'dummy', NULL
WHERE NOT EXISTS (
    SELECT 1 FROM email_delivery_providers WHERE name = 'dummy-backup'
);
