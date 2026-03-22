"""
Alembic environment for core-auth.

Run from ``services/core-auth`` with ``DATABASE_URL`` set (same as the app).
Plain ``postgresql://`` in the environment is coerced to ``postgresql+psycopg://`` in ``get_url()``.
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine

# Project root: parent of ``alembic/`` (contains ``app/``)
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.core.config import DATABASE_URL  # noqa: E402
from app.core.orm_base import Base  # noqa: E402

# Register all models on Base.metadata (required for autogenerate)
from app.models.client import Client  # noqa: E402, F401
from app.models.email_delivery_provider import EmailDeliveryProvider  # noqa: E402, F401
from app.models.email_log import EmailLog  # noqa: E402, F401
from app.models.plan import Plan  # noqa: E402, F401
from app.models.plan_quota import PlanQuota  # noqa: E402, F401
from app.models.quota import Quota  # noqa: E402, F401
from app.models.service import Service  # noqa: E402, F401
from app.models.usage import Usage  # noqa: E402, F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        url = DATABASE_URL
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://")
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(get_url(), future=True, pool_pre_ping=True)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
