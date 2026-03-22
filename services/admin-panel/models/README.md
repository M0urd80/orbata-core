# Sequelize models (read-only mapping)

| Owner | **core-auth** (SQLAlchemy) — single source of truth for schema |
|-------|------------------------------------------------------------------|
| This app | **Maps** existing tables only — **no** `sequelize.sync()`, **no** `force`, **no** migrations |

`tableName` values **must** match Postgres / SQLAlchemy `__tablename__` exactly:

| SQLAlchemy (`core-auth`) | Sequelize `tableName` |
|--------------------------|------------------------|
| `plans` | `plans` |
| `services` | `services` |
| `quotas` | `quotas` |
| `plan_quotas` | `plan_quotas` |
| `clients` | `clients` |
| `email_logs` | `email_logs` |
| `usage` | `usage` |

Every model uses:

- `timestamps: false` (columns are explicit; no `createdAt` / `updatedAt` inference)
- `freezeTableName: true` (per model + default in `db.js`) — no pluralization of names

Connection string: **`ADMIN_DATABASE_URL`** (preferred) or **`DATABASE_URL`**, normalized so SQLAlchemy URLs like `postgresql+psycopg://` become `postgres://` for Sequelize. In Docker Compose use **`postgresql+psycopg://orbata:orbata@postgres:5432/orbata`** (host **`postgres`**, not `localhost`).

**Verify from the admin container** (tables should list — if “No relations”, wrong DB URL). The Node image has no `psql` until you install the client:

```sh
docker exec -it orbata-core-admin-panel-1 sh
apk add --no-cache postgresql-client
psql "$DATABASE_URL" -c '\dt'
```

Compose `depends_on: [core-auth]` only starts order — the app still **waits for `public.plans`** via `waitForTables()` before starting AdminJS.

All models share **one** `sequelize` instance from `db.js` (each model file does `import { sequelize } from './db.js'`).

**Admin entrypoint:** import `Plan`, `Service`, `sequelize`, etc. only from `./models/index.js` so associations run and there is never a second Sequelize instance.

**AdminJS (Sequelize):** FK `reference` must be the **resource id** (Sequelize `tableName` string), e.g. `plans` / `services` / `quotas` — not the model class. Register **Plan**, **Service**, **Quota** before **PlanQuota** and **Usage**.

**`created_at`:** SQLAlchemy models use `server_default=now()` where applicable (`plans`, `services`, `clients`, `email_logs`). Sequelize mirrors with `defaultValue: DataTypes.NOW` for Admin. Existing databases without a column default can run:  
`ALTER TABLE clients ALTER COLUMN created_at SET DEFAULT now();` (and the same for `email_logs` if needed).

**Model:** Reusable caps live in **`quotas`**: **`service_id`** + **`quota_daily`** (user-edited). **`quota_monthly`** is always **`quota_daily × 30`** (derived in core-auth + admin `before` hooks). **`name`** is auto-generated for UI (e.g. `EMAIL-200/day`) and is **`isTitle`** on the Quota resource so **Package quotas** dropdowns stay human-readable. **`plan_quotas`** is the link table **`(plan_id, quota_id)`** only. Clients carry **`plan_id`** only. OTP resolves **plan → plan_quotas → quotas** where `quotas.service_id` matches the channel (e.g. email). **`usage.sent_count`** is per client/day/**`service_id`**. Postgres: **`uq_plan_quota_plan_quota_id`** UNIQUE `(plan_id, quota_id)`.

**Admin UX:** **Packages** → **Tiers**, **Quotas** (channel + daily only), **Package quotas** (link). Grouped list: `components/PlanQuotaList.jsx`. Each package must keep **≥ 1** link (delete guard + SQLAlchemy hook in core-auth). Startup migration in core-auth moves legacy `plan_quotas` rows that stored limits inline into **`quotas`**.
