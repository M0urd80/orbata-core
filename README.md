# Orbata Core

Orbata Core is a lightweight authentication and OTP verification engine with API-key–protected access, PostgreSQL-backed clients, Redis queues for email delivery, and per-client usage and rate limits.

---

## Features

- **OTP** — Generate and verify email OTPs (hashed storage, TTL, max attempts)
- **API keys** — Prefixed keys (`orb_live_…`), SHA-256 stored in DB; raw key shown only at create/rotate
- **PostgreSQL** — `clients` table (id, name, hashed api_key, created_at, optional expiration/rotation metadata)
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
| `POST` | `/otp/send`    | `x-api-key` | Send OTP (JSON body and/or `?email=` query supported) |
| `POST` | `/otp/verify`  | `x-api-key` | Verify OTP (JSON and/or `?email=&otp=` query supported) |

**Send** — Per-client rate limit (default 10/min per client), per-email/IP limits, idempotency lock (60s), then enqueue for email.

**Verify** — Validates 6-digit OTP; too many failures can return **429**.

### Admin

| Method | Path                           | Auth              | Description |
|--------|--------------------------------|-------------------|-------------|
| `POST` | `/admin/clients`               | `x-admin-secret`  | Create client; returns `client_id` + **raw `api_key` once** |
| `GET`  | `/admin/usage/{client_id}`     | `x-admin-secret`  | Daily **Postgres** aggregates: `[{ date, sent_count, success_count, fail_count }, …]` (newest first) |
| `GET`  | `/admin/logs/{client_id}`      | `x-admin-secret`  | Last **50** email send attempts for that client (Postgres), newest first |
| `POST` | `/admin/clients/{id}/rotate`   | `x-admin-secret`  | Rotate API key; returns new raw key once |

---

## Rate limiting (Redis) and usage (Postgres)

**Usage** — Table **`usage`**: one row per **client_id + UTC calendar date + channel** (`email`). `sent_count` increments on `/otp/send`; **`email-service`** increments `success_count` / `fail_count` after each SMTP attempt.

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

Create a client (save the returned `api_key`):

```bash
curl -s -X POST "http://localhost:8101/admin/clients" \
  -H "Content-Type: application/json" \
  -H "x-admin-secret: YOUR_ADMIN_SECRET" \
  -d "{\"name\": \"My App\"}"
```

Send OTP (query param):

```bash
curl -s -X POST "http://localhost:8101/otp/send?email=test@example.com" \
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
