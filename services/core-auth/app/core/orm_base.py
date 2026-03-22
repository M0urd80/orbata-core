"""SQLAlchemy declarative base shared by all ORM models (runtime + Alembic)."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
