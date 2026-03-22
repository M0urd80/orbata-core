# Alembic migrations (core-auth)

Schema migrations for the PostgreSQL database used by **core-auth** (and shared with admin-panel / email-worker).

## Setup

From **`orbata-core/services/core-auth`** (or `/app` in the core-auth container):

```bash
pip install -r requirements.txt
export DATABASE_URL="postgresql+psycopg://orbata:orbata@localhost:5432/orbata"
```

Use the same URL as production (Compose: `postgresql+psycopg://orbata:orbata@postgres:5432/orbata`).

## Create a revision (autogenerate)

After changing SQLAlchemy models under `app/models/`:

```bash
alembic revision --autogenerate -m "add provider table"
```

Review the generated file under `alembic/versions/` before committing.

## Apply migrations

```bash
alembic upgrade head
```

Rollback one revision:

```bash
alembic downgrade -1
```

## Docker

The **core-auth** image runs `alembic upgrade head` before `uvicorn` so every container start applies pending migrations.

## Notes

- **`app.core.orm_base.Base`** holds shared metadata; **`app.core.database`** must not be imported from Alembic (it connects on import).
- **Fresh database:** `001_initial_schema` creates all tables including **`email_delivery_providers`**.
- **Existing database** that already had tables from `create_all`: either run migrations on a copy and verify, or after backing up run `alembic stamp 001_initial_schema` once if the schema already matches, then use `revision --autogenerate` for future changes.
- **`init_db_schema()`** on FastAPI startup still runs idempotent seeds and legacy SQL fixes (no `create_all`).
