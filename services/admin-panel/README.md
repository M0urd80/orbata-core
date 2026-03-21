# Orbata Admin Panel (AdminJS)

Web UI for **Postgres** tables `clients` and `email_logs`.

- **URL:** `http://localhost:3000/admin` (Compose uses **`3000:3000`**; use **`127.0.0.1:3000:3000`** in `docker-compose.yml` if you want localhost-only access).
- **Auth:** **`buildAuthenticatedRouter`**. Set **`ADMIN_USER`** and **`ADMIN_PASSWORD`** in **`.env`**.
- **Sessions:** **`connect-redis`** + **`redis`** (same Redis as core-auth). Env: **`REDIS_HOST`** (default `redis`), **`REDIS_PORT`** (default `6379`). Key prefix: `orbata:admin:sess:`.
- **UI:** **Core → Customers**, **Monitoring → OTP Logs**; **`api_key`** hidden; **`id`** read-only on Customer; OTP logs sorted newest-first, filter **status** / **client_id**, search **email**.
- **DB startup:** Retries Postgres and Redis (**`REDIS_MAX_RETRIES`**, **`REDIS_RETRY_DELAY_MS`**).

Requires the same Postgres instance as **core-auth** (`orbata` / `orbata` / database `orbata`).

Set in **`.env`** (required for login):

```env
ADMIN_USER=admin
ADMIN_PASSWORD=your-strong-password
```

**Session / cookies:** If login misbehaves after config changes, use **Incognito** or **clear site data for `localhost:3000`** (old session cookies conflict with new secrets).

This package uses **`"type": "module"`** and **`index.js`** as native ES modules (`import` / `export`).
