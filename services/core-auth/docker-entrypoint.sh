#!/bin/sh
# Run DB migrations before the API. If migrations fail, exit non-zero so the container stops.

set -u

echo "[core-auth] Running Alembic migrations: alembic upgrade head"
if ! alembic upgrade head; then
  echo "[core-auth] FATAL: alembic upgrade head failed — check DATABASE_URL, Postgres reachability, and migration revisions. Exiting."
  exit 1
fi

echo "[core-auth] Migrations applied OK; starting uvicorn"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
