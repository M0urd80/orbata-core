-- SMS failover chain: Twilio first (priority 0), dummy log-only backup (priority 10).

INSERT INTO email_delivery_providers
    (name, service, priority, is_active, provider_kind, config)
SELECT 'twilio-primary', 'sms', 0, true, 'twilio', NULL
WHERE NOT EXISTS (
    SELECT 1 FROM email_delivery_providers WHERE name = 'twilio-primary'
);

INSERT INTO email_delivery_providers
    (name, service, priority, is_active, provider_kind, config)
SELECT 'dummy-backup', 'sms', 10, true, 'dummy', NULL
WHERE NOT EXISTS (
    SELECT 1 FROM email_delivery_providers WHERE name = 'dummy-backup'
);
