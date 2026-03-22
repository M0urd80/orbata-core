-- Allow creating clients without a plan; assign later in Admin.
-- OTP send requires a plan (core-auth returns 400 until assigned).

ALTER TABLE clients ALTER COLUMN plan_id DROP NOT NULL;
