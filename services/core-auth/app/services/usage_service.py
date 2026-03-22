from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import desc, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.plan_quota import PlanQuota
from app.models.quota import Quota
from app.models.service import Service
from app.models.usage import Usage, utc_today

# Channel names in ``services`` (OTP email / SMS / future channels)
SERVICE_NAME = "email"
SERVICE_NAME_EMAIL = SERVICE_NAME  # backward compatibility
SERVICE_NAME_SMS = "sms"
SERVICE_NAME_WHATSAPP = "whatsapp"


def _quota_cap(value: int | None) -> int | None:
    """
    Enforced cap only when value is a positive int.
    ``None`` or ``<= 0`` → unlimited (skip quota check; matches ``0 = unlimited`` in ``Quota``).
    """
    if value is None:
        return None
    if value <= 0:
        return None
    return value


def get_service(db: Session, name: str) -> Service | None:
    """Resolve delivery channel by catalog name (e.g. ``email``)."""
    return db.execute(select(Service).where(Service.name == name)).scalars().first()


def get_service_by_name(db: Session, name: str) -> Service | None:
    return get_service(db, name)


def get_service_id_by_name(db: Session, name: str) -> uuid.UUID | None:
    row = get_service(db, name)
    return row.id if row else None


def get_quota_for_plan_and_service(
    db: Session, plan_id: uuid.UUID | None, service_id: uuid.UUID
) -> Quota | None:
    """
    Resolve the ``Quota`` row for a client's plan and a channel (e.g. email):
    ``plan_quotas`` → ``quotas`` where ``quotas.service_id`` matches.
    Missing link → unlimited for that axis.
    """
    if plan_id is None:
        return None
    stmt = (
        select(Quota)
        .join(PlanQuota, PlanQuota.quota_id == Quota.id)
        .where(PlanQuota.plan_id == plan_id, Quota.service_id == service_id)
    )
    return db.execute(stmt).scalars().first()


def _effective_quota_daily(quota: Quota | None) -> int | None:
    """``<= 0`` = unlimited (no enforcement)."""
    return _quota_cap(quota.quota_daily) if quota else None


def _effective_quota_monthly(quota: Quota | None) -> int | None:
    return _quota_cap(quota.quota_monthly) if quota else None


def resolve_effective_quota_daily(
    client: Client, db: Session, *, service_id: uuid.UUID
) -> int | None:
    q = get_quota_for_plan_and_service(db, client.plan_id, service_id)
    return _quota_cap(q.quota_daily) if q else None


def resolve_effective_quota_monthly(
    client: Client, db: Session, *, service_id: uuid.UUID
) -> int | None:
    q = get_quota_for_plan_and_service(db, client.plan_id, service_id)
    return _quota_cap(q.quota_monthly) if q else None


def _parse_client_id(client_id: str) -> uuid.UUID:
    return uuid.UUID(str(client_id))


def increment_sent(db: Session, client_id: str, *, service_id: uuid.UUID) -> None:
    """Upsert: +1 sent_count for (client, UTC date, service_id)."""
    cid = _parse_client_id(client_id)
    today = utc_today()
    stmt = (
        pg_insert(Usage)
        .values(
            id=uuid.uuid4(),
            client_id=cid,
            date=today,
            service_id=service_id,
            sent_count=1,
            success_count=0,
            fail_count=0,
        )
        .on_conflict_do_update(
            constraint="uq_usage_client_date_service_id",
            set_={"sent_count": Usage.sent_count + 1},
        )
    )
    db.execute(stmt)
    db.commit()


def increment_usage(db: Session, client_id: str, *, service_id: uuid.UUID) -> None:
    """After successful OTP enqueue: bump Usage.sent_count (same as increment_sent)."""
    increment_sent(db, client_id, service_id=service_id)


def get_daily_sent(db: Session, client_id: uuid.UUID, service_id: uuid.UUID) -> int:
    today = utc_today()
    row = db.execute(
        select(Usage).where(
            Usage.client_id == client_id,
            Usage.date == today,
            Usage.service_id == service_id,
        )
    ).scalars().first()
    return int(row.sent_count) if row else 0


def get_monthly_sent_sum(db: Session, client_id: uuid.UUID, service_id: uuid.UUID) -> int:
    month_start = utc_today().replace(day=1)
    stmt = select(func.coalesce(func.sum(Usage.sent_count), 0)).where(
        Usage.client_id == client_id,
        Usage.date >= month_start,
        Usage.service_id == service_id,
    )
    return int(db.execute(stmt).scalar_one())


def check_monthly_quota(
    db: Session,
    *,
    client: Client,
    service: Service,
    quota: Quota | None,
) -> None:
    """Monthly cap vs DB ``Usage.sent_count`` sum (UTC month)."""
    sid = service.id
    eff_monthly = _effective_quota_monthly(quota)
    if eff_monthly is not None:
        if get_monthly_sent_sum(db, client.id, sid) >= eff_monthly:
            raise HTTPException(status_code=429, detail="Monthly quota exceeded")


def check_quota(
    db: Session,
    *,
    client: Client,
    service: Service,
    quota: Quota | None,
) -> None:
    """
    Enforce ``quotas`` caps (via plan links) against ``usage.sent_count``
    (UTC day + UTC calendar month). OTP ``/send`` uses this path.
    """
    sid = service.id
    eff_daily = _effective_quota_daily(quota)
    if eff_daily is not None:
        if get_daily_sent(db, client.id, sid) >= eff_daily:
            raise HTTPException(status_code=429, detail="Daily quota exceeded")
    check_monthly_quota(db, client=client, service=service, quota=quota)


def list_usage_for_client(
    db: Session, client_id: str, limit: int = 366
) -> list[dict]:
    """Recent usage rows with client + service names (admin API)."""
    cid = _parse_client_id(client_id)
    stmt = (
        select(Usage, Client.name, Service.name)
        .join(Client, Usage.client_id == Client.id)
        .join(Service, Usage.service_id == Service.id)
        .where(Usage.client_id == cid)
        .order_by(desc(Usage.date), desc(Usage.service_id))
        .limit(limit)
    )
    rows = db.execute(stmt).all()
    return [
        {
            "client_id": str(usage_row.client_id),
            "client_name": client_name,
            "service_id": str(usage_row.service_id),
            "service_name": service_name,
            "date": usage_row.date.isoformat(),
            "sent": usage_row.sent_count,
            "success": usage_row.success_count,
            "fail": usage_row.fail_count,
        }
        for usage_row, client_name, service_name in rows
    ]
