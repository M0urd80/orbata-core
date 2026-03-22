-- Tear down temporary failover test row (restore normal WhatsApp routing).

DELETE FROM email_delivery_providers
WHERE name = 'failover-test';
