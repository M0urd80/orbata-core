"""Record provider send outcomes and auto-disable after repeated failures."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.provider_health import ProviderHealth


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_or_create(db: Session, provider_name: str, service: str) -> ProviderHealth:
    stmt = select(ProviderHealth).where(
        ProviderHealth.provider_name == provider_name,
        ProviderHealth.service == service,
    )
    row = db.execute(stmt).scalars().first()
    if row is not None:
        return row
    row = ProviderHealth(
        id=uuid.uuid4(),
        provider_name=provider_name,
        service=service,
        success_count=0,
        failure_count=0,
        disabled=False,
    )
    db.add(row)
    try:
        db.commit()
        db.refresh(row)
        return row
    except IntegrityError:
        db.rollback()
        row = (
            db.execute(
                select(ProviderHealth).where(
                    ProviderHealth.provider_name == provider_name,
                    ProviderHealth.service == service,
                )
            )
            .scalars()
            .first()
        )
        if row is None:
            raise
        return row


def record_success(db: Session, provider_name: str, service: str) -> ProviderHealth:
    row = get_or_create(db, provider_name, service)
    row.success_count = int(row.success_count or 0) + 1
    row.last_success_at = _now()
    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    return row


def record_failure(db: Session, provider_name: str, service: str) -> ProviderHealth:
    row = get_or_create(db, provider_name, service)
    row.failure_count = int(row.failure_count or 0) + 1
    row.last_failure_at = _now()
    row.updated_at = _now()
    if row.failure_count >= 3:
        row.disabled = True
    db.commit()
    db.refresh(row)
    return row
