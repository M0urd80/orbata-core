# Orbata Admin Panel (AdminJS)

Web UI for **Postgres** tables `clients` and `email_logs`.

- **URL:** `http://localhost:3000/admin` (Compose uses **`3000:3000`**; use **`127.0.0.1:3000:3000`** in `docker-compose.yml` if you want localhost-only access).
- **Auth:** Always **`buildAuthenticatedRouter`**. Set **`ADMIN_USER`** and **`ADMIN_PASSWORD`** in **`.env`** (also accepts legacy `ADMIN_PANEL_*`). Use long random values in production.
- **Secrets:** Hashed API keys in DB are **hidden** in AdminJS list/show/filter/edit for `api_key`.
- **DB startup:** Retries Postgres (**`DB_MAX_RETRIES`**, **`DB_RETRY_DELAY_MS`**) like core-auth.

Requires the same Postgres instance as **core-auth** (`orbata` / `orbata` / database `orbata`).

Set in **`.env`** (required for login):

```env
ADMIN_USER=admin
ADMIN_PASSWORD=your-strong-password
```

**Session / cookies:** If login misbehaves after config changes, use **Incognito** or **clear site data for `localhost:3000`** (old session cookies conflict with new secrets).

This package uses **`"type": "module"`** and **`index.js`** as native ES modules (`import` / `export`).
