-- Run once after deploying Client model without quota_daily / quota_monthly.
-- Quotas live only in plan_quotas (per plan + service).

ALTER TABLE clients DROP COLUMN IF EXISTS quota_daily;
ALTER TABLE clients DROP COLUMN IF EXISTS quota_monthly;
