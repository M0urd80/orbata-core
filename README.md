# Orbata Core

Orbata Core is a lightweight authentication and OTP verification engine with API-key–protected access, PostgreSQL-backed clients, Redis queues for email delivery, and per-client usage and rate limits.

---

## Features

- **OTP** — Generate and verify email OTPs (hashed storage, TTL, max attempts)
- **API keys** — Prefixed keys (`orb_live_…`), SHA-256 stored in DB; raw key shown only at create/rotate
- **PostgreSQL** — `clients` (required **`plan_id`** → `plans`, **`ON DELETE RESTRICT`**), hashed api_key, optional quota overrides, etc.
- **Redis** — OTP storage, locks, email/IP rate buckets, **per-client** minute windows, usage counters, email queues
- **Async email** — Core enqueues; worker sends via SMTP; retry with jitter + ZSET delay; DLQ with failure metadata
- **Email audit** — `email_logs` in Postgres (per send: client, recipient, status, attempts, error, timestamp)
- **Docker** — `docker compose` for core-auth, Postgres, Redis, email worker, and retry worker

---

## Architecture

```
Client (x-api-key)
    → Core API (FastAPI)
        → PostgreSQL (clients / API key validation)
        → Redis (OTP, rate limits, locks); Postgres **`usage`** (daily aggregates)
        → Redis list email_queue
    → Email worker → SMTP
    → Retry worker (ZSET) → requeue to email_queue
    → DLQ on permanent failure
```

---

## Run locally

```bash
cd orbata-core
docker compose up --build
```

| Service      | URL / port        |
|-------------|-------------------|
| Core API    | `http://localhost:8101` |
| AdminJS UI  | `http://localhost:3000/admin` (Postgres: `clients`, `email_logs`) |
| PostgreSQL  | `localhost:5432`  |
| Redis       | `localhost:6379`  |

### Database migrations (Alembic)

Schema for **core-auth** is defined in SQLAlchemy models under `services/core-auth/app/models/`. [Alembic](https://alembic.sqlalchemy.org/) lives in `services/core-auth/alembic/` (see `alembic/README.md`).

```bash
cd services/core-auth
export DATABASE_URL="postgresql+psycopg://orbata:orbata@localhost:5432/orbata"
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

`DATABASE_URL` must match the running Postgres (from `.env` or Compose).

- **Docker:** **core-auth** runs **`alembic upgrade head`** before **uvicorn** (see `services/core-auth/Dockerfile`).
- **Seeds / legacy fixes:** **`init_db_schema()`** still runs on startup but no longer calls **`create_all`** — schema is owned by Alembic.

Rollback one migration: `alembic downgrade -1`.

---

## Authentication

### OTP routes (`/otp/*`)

Every OTP request must include a valid API key:

| Header       | Description        |
|-------------|--------------------|
| `x-api-key` | Client’s **raw** API key (only known at issuance; DB stores hash) |

Missing or invalid key → **401**. Expired key → **401** with an appropriate message.

### Admin routes (`/admin/*`)

| Header           | Description                          |
|-----------------|--------------------------------------|
| `x-admin-secret` | Must match `ADMIN_SECRET` in `.env` |

Invalid secret → **403**.

### AdminJS (`/admin` on port 3000)

- **Port:** **`3000:3000`** by default (reachable on the host at `http://localhost:3000/admin`). To restrict to this machine only, use **`127.0.0.1:3000:3000`** in Compose.
- **Login:** **`ADMIN_USER`** / **`ADMIN_PASSWORD`** in **`.env`** (fallback: legacy `ADMIN_PANEL_*`, then insecure defaults—set real values in prod).
- **Cookies/session:** **`ADMINJS_COOKIE_SECRET`** and **`ADMINJS_SESSION_SECRET`** (32+ chars). **`NODE_ENV=production`** in Compose enables stricter cookie flags.

---

## API reference

### Health

| Method | Path | Auth |
|--------|------|------|
| `GET`  | `/`  | None |

### OTP

| Method | Path           | Auth        | Description |
|--------|----------------|-------------|-------------|
| `POST` | `/otp/send`    | `x-api-key` | Send OTP: **exactly one** of **`email`** or **`sms`** (E.164, e.g. `+15551234567`) via JSON and/or `?email=` / `?sms=` |
| `POST` | `/otp/verify`  | `x-api-key` | Verify OTP: same identifier (`email` or `sms`) + `otp` (JSON and/or query) |

**Send** — Per-client rate limit (default 10/min per client), per-identifier/IP limits, idempotency lock (60s). **Email** jobs → SMTP routing; **SMS** → Twilio routing (worker reads `email_delivery_providers` for `service = sms`).

**Verify** — Validates 6-digit OTP against the same identifier used on send; too many failures can return **429**.

### Admin

| Method | Path                           | Auth              | Description |
|--------|--------------------------------|-------------------|-------------|
| `POST` | `/admin/plans`                 | `x-admin-secret`  | Create plan (`name`, `price` default **0**). Limits: **`plan_quotas`** with **`service_id`** → **`services`** (seeded **email**, **sms**) |
| `GET`  | `/admin/plans`                 | `x-admin-secret`  | List plans |
| `DELETE` | `/admin/plans/{plan_id}`     | `x-admin-secret`  | Delete plan — **fails** if any **client** references it (`ON DELETE RESTRICT`) |
| `POST` | `/admin/clients`               | `x-admin-secret`  | Create client; **required** **`plan_id`** (UUID); returns `client_id` + **raw `api_key` once** |
| `GET`  | `/admin/usage/{client_id}`     | `x-admin-secret`  | Daily aggregates: `[{ client_id, client_name, service_id, service_name, date, sent, success, fail }, …]` (newest first) |
| `GET`  | `/admin/logs/{client_id}`      | `x-admin-secret`  | Last **50** email send attempts for that client (Postgres), newest first |
| `POST` | `/admin/clients/{id}/rotate`   | `x-admin-secret`  | Rotate API key; returns new raw key once |

---

## Rate limiting (Redis) and usage (Postgres)

**Usage** — Table **`usage`**: one row per **client_id + UTC calendar date + `service_id`**. `sent_count` increments on `/otp/send` for the **`email`** or **`sms`** service row (depending on channel); **`email-service`** bumps **`success_count` / `fail_count`** for that **`service_id`** (included in the Redis job payload).

**Plans & quotas** — **`services`**: **`email`** + **`sms`** (auto-seeded on core-auth startup). **`plan_quotas`**: link each plan to quotas per channel. **`/otp/send`** resolves **`PlanQuota`** for the active channel. **AdminJS**: **Services**, **Plans**, **Plan quotas**, **Usage**. **`clients.quota_*`** override **email** caps only.

*Existing databases* (if `create_all` did not add objects):

```sql
CREATE TABLE IF NOT EXISTS plans (
  id UUID PRIMARY KEY,
  name VARCHAR(255) NOT NULL UNIQUE,
  price DOUBLE PRECISION NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS services (
  id UUID PRIMARY KEY,
  name VARCHAR(64) NOT NULL UNIQUE,
  description VARCHAR(512) NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS plan_quotas (
  id UUID PRIMARY KEY,
  plan_id UUID NOT NULL REFERENCES plans(id) ON DELETE CASCADE,
  service_id UUID NOT NULL REFERENCES services(id) ON DELETE RESTRICT,
  quota_daily INTEGER NOT NULL DEFAULT 0,
  quota_monthly INTEGER NOT NULL DEFAULT 0,
  UNIQUE (plan_id, service_id)
);
CREATE INDEX IF NOT EXISTS ix_plan_quotas_plan_id ON plan_quotas (plan_id);
CREATE INDEX IF NOT EXISTS ix_plan_quotas_service_id ON plan_quotas (service_id);
ALTER TABLE clients ADD COLUMN IF NOT EXISTS plan_id UUID REFERENCES plans(id);
UPDATE clients SET plan_id = (SELECT id FROM plans ORDER BY name LIMIT 1) WHERE plan_id IS NULL;
-- plan_id may stay NULL (assign later in Admin). OTP returns 400 until a plan is set.
-- To force NOT NULL after backfilling: ALTER TABLE clients ALTER COLUMN plan_id SET NOT NULL;
ALTER TABLE clients DROP CONSTRAINT IF EXISTS clients_plan_id_fkey;
ALTER TABLE clients ADD CONSTRAINT clients_plan_id_fkey
  FOREIGN KEY (plan_id) REFERENCES plans(id) ON DELETE RESTRICT;
CREATE INDEX IF NOT EXISTS ix_clients_plan_id ON clients (plan_id);
-- Per-client quota columns removed; caps are only in plan_quotas (plan + service).
ALTER TABLE clients DROP COLUMN IF EXISTS quota_daily;
ALTER TABLE clients DROP COLUMN IF EXISTS quota_monthly;
CREATE TABLE IF NOT EXISTS usage (
  id UUID PRIMARY KEY,
  client_id UUID NOT NULL,
  date DATE NOT NULL,
  service_id UUID NOT NULL REFERENCES services(id) ON DELETE RESTRICT,
  sent_count INTEGER NOT NULL DEFAULT 0,
  success_count INTEGER NOT NULL DEFAULT 0,
  fail_count INTEGER NOT NULL DEFAULT 0,
  UNIQUE (client_id, date, service_id)
);
CREATE INDEX IF NOT EXISTS ix_usage_client_id ON usage (client_id);
CREATE INDEX IF NOT EXISTS ix_usage_service_id ON usage (service_id);
```

**Migrate `usage.channel` (string) → `service_id` (FK):**

```sql
ALTER TABLE usage ADD COLUMN IF NOT EXISTS service_id UUID REFERENCES services(id);
UPDATE usage u
SET service_id = s.id
FROM services s
WHERE u.service_id IS NULL AND s.name = u.channel;
ALTER TABLE usage DROP COLUMN IF EXISTS channel;
ALTER TABLE usage ALTER COLUMN service_id SET NOT NULL;
DROP INDEX IF EXISTS uq_usage_client_date_channel;
CREATE UNIQUE INDEX IF NOT EXISTS uq_usage_client_date_service_id ON usage (client_id, date, service_id);
```

**Migrate `plan_quotas.service` (string) → `service_id` (FK):**

```sql
INSERT INTO services (id, name, description, created_at)
SELECT gen_random_uuid(), v.name, NULL, now()
FROM (VALUES ('email'), ('sms')) AS v(name)
WHERE NOT EXISTS (SELECT 1 FROM services s WHERE s.name = v.name);

ALTER TABLE plan_quotas ADD COLUMN IF NOT EXISTS service_id UUID REFERENCES services(id);
UPDATE plan_quotas pq
SET service_id = s.id
FROM services s
WHERE pq.service_id IS NULL AND s.name = pq.service;
ALTER TABLE plan_quotas DROP COLUMN IF EXISTS service;
ALTER TABLE plan_quotas ALTER COLUMN service_id SET NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_plan_quota_plan_service_id ON plan_quotas (plan_id, service_id);
```

**Migrate old `plans.quota_*` into `plan_quotas` (email service), then drop legacy columns:**

```sql
-- Ensure `services` + `email` row exist (see seed or INSERT above).
INSERT INTO plan_quotas (id, plan_id, service_id, quota_daily, quota_monthly)
SELECT gen_random_uuid(), p.id, s.id, p.quota_daily, p.quota_monthly
FROM plans p
CROSS JOIN services s
WHERE s.name = 'email'
  AND NOT EXISTS (
    SELECT 1 FROM plan_quotas pq
    WHERE pq.plan_id = p.id AND pq.service_id = s.id
  );
-- optional: ALTER TABLE plans DROP COLUMN IF EXISTS quota_daily, DROP COLUMN IF EXISTS quota_monthly;
```

**Keep data, fix `plans` defaults (Postgres):**

```sql
ALTER TABLE plans ALTER COLUMN created_at SET DEFAULT now();
ALTER TABLE plans ALTER COLUMN price SET DEFAULT 0;
UPDATE plans SET created_at = now() WHERE created_at IS NULL;
UPDATE plans SET price = 0 WHERE price IS NULL;
```

| Key pattern | Purpose |
|-------------|---------|
| `rate:{client_id}:{YYYY-MM-DD-HH-MM}` | Per-client requests per UTC minute (default limit: **10**; `CLIENT_RATE_LIMIT`) |
| `rate:{email}` / `rate:{ip}` | Legacy per-email and per-IP buckets |
| `otp:lock:{email}` | Idempotency: block duplicate sends for 60s |

---

## Reliability (email pipeline)

| Redis structure | Role |
|-----------------|------|
| `email_queue` (list) | New OTP email jobs |
| `email_retry_zset` (sorted set) | Delayed retries (`score` = `next_try_at`) |
| `email_dlq` (list) | Failed jobs after max attempts (includes `failure_reason`, `final_attempt_at`, `total_attempts`) |

Retries use exponential backoff **+ jitter**. A separate **email-retry** container moves due jobs from the ZSET back to `email_queue`.

### Multi-provider routing (failover)

The email worker loads **`email_delivery_providers`** from Postgres: filter **`is_active`**, match **`service`** to the channel name (from the job’s **`service_id`** → **`services.name`**, e.g. `email`), order by **`priority` ASC** (lower = tried first). It calls **`send()`** on each implementation in order; **first success wins**. If **all** providers fail for that processing attempt, the job is retried / **DLQ**’d like any other failure.

| Column | Purpose |
|--------|---------|
| `service` | Same string as **`services.name`** (`email`, …) |
| `priority` | Integer; lower value = earlier in failover chain |
| `is_active` | Inactive rows are skipped |
| `provider_kind` | `smtp` / `smtp_env` / `brevo` → SMTP; **`twilio`** → SMS (Twilio REST); **`dummy`** → log-only SMS (dev / failover) |
| `config` | Optional JSON: SMTP keys above, or Twilio: `account_sid`, `auth_token`, `from_number` / `phone_number` |

**SQL:** `services/email-service/sql/create_email_delivery_providers.sql` (new DBs). Existing DBs: run **`alter_email_delivery_providers_kind_config.sql`**. Seed SMS row: **`services/email-service/sql/seed_sms_twilio_provider.sql`**. If **no rows** exist for **`email`**, the worker uses **env SMTP**; for **`sms`**, **env Twilio** (`TWILIO_*`).

---

## Environment variables

Create **`orbata-core/.env`** (do not commit secrets; `.env` is gitignored).

**SMTP (email worker)**

```env
SMTP_SERVER=smtp-relay.brevo.com
SMTP_PORT=587
SMTP_LOGIN=your_smtp_login
SMTP_PASSWORD=your_smtp_key
FROM_EMAIL=no-reply@yourdomain.com
```

**Twilio (SMS OTP — same worker container)**

```env
TWILIO_ACCOUNT_SID=ACxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=+15551234567
```

**Admin**

```env
ADMIN_SECRET=your_long_random_secret
```

**Core (optional overrides)**

```env
CLIENT_RATE_LIMIT=10
REDIS_HOST=redis
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=orbata
POSTGRES_USER=orbata
POSTGRES_PASSWORD=orbata
DATABASE_URL=postgresql+psycopg://orbata:orbata@postgres:5432/orbata
```

Use the same **`DATABASE_URL`** for **core-auth** and **email-service** so the worker can write **`email_logs`** to Postgres.

⚠️ Rotate any credential that was ever committed or shared.

---

## Testing (examples)

Create a plan, then a client on that plan (save the returned `api_key`):

```bash
curl -s -X POST "http://localhost:8101/admin/plans" \
  -H "Content-Type: application/json" \
  -H "x-admin-secret: YOUR_ADMIN_SECRET" \
  -d "{\"name\": \"Free\", \"price\": 0}"

# Add email quotas in AdminJS (Plan quotas) or SQL, e.g. plan_id + service email + quota_daily 100

curl -s -X POST "http://localhost:8101/admin/clients" \
  -H "Content-Type: application/json" \
  -H "x-admin-secret: YOUR_ADMIN_SECRET" \
  -d "{\"name\": \"My App\", \"plan_id\": \"PLAN_UUID_HERE\"}"
```

Send OTP (email or SMS, query param):

```bash
curl -s -X POST "http://localhost:8101/otp/send?email=test@example.com" \
  -H "x-api-key: YOUR_RAW_API_KEY"

curl -s -X POST "http://localhost:8101/otp/send?sms=%2B15551234567" \
  -H "x-api-key: YOUR_RAW_API_KEY"
```

Usage history for a client (newest dates first):

```bash
curl -s "http://localhost:8101/admin/usage/CLIENT_UUID" \
  -H "x-admin-secret: YOUR_ADMIN_SECRET"
```

---

## Version notes

### v0.2 — Async OTP delivery

- Redis queue + dedicated email worker + SMTP delivery

### v0.3 — Reliability layer

- ZSET-based delayed retries, jitter, DLQ enrichment, structured worker logging (where configured)

### Current — API keys, Postgres, usage, per-client limits

- Hashed API keys, optional expiration/rotation, admin client CRUD hooks, usage counters, per-client minute rate limiting

---

## Project layout (high level)

```
orbata-core/
├── services/
│   ├── core-auth/          # FastAPI OTP + admin + middleware
│   └── email-service/      # worker.py, retry_worker.py
├── docker-compose.yml
├── .env
└── README.md
```
