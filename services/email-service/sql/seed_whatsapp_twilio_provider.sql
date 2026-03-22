-- WhatsApp via Twilio: ``from_number`` must be a WhatsApp-enabled sender (DB-only; no env fallback).

INSERT INTO email_delivery_providers (
    name, service, priority, is_active, provider_kind, config
)
SELECT
    'twilio-whatsapp',
    'whatsapp',
    0,
    true,
    'twilio',
    '{"from_number": "whatsapp:+14155238886"}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM email_delivery_providers WHERE name = 'twilio-whatsapp'
);
