from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, event, select, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.orm_base import Base
from app.models.service import Service


class Quota(Base):
    """
    Reusable limit: channel (service) + daily cap; monthly = daily × 30; human ``name`` for UI.
    """

    __tablename__ = "quotas"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("services.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        server_default=text("''"),
    )
    quota_daily: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    quota_monthly: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("now()"),
    )

    service_row: Mapped["Service"] = relationship(
        "Service", back_populates="quotas"
    )
    plan_links: Mapped[list["PlanQuota"]] = relationship(
        "PlanQuota", back_populates="quota_row"
    )


def _quota_derive_name_and_monthly(connection, target: Quota) -> None:
    """``quota_monthly = quota_daily * 30``; ``name = SERVICE-NNN/day``."""
    row = connection.execute(
        select(Service.name).where(Service.id == target.service_id)
    ).one_or_none()
    if row is None:
        raise ValueError("Quota.service_id must reference an existing service")
    svc_name = row[0]
    d = int(target.quota_daily if target.quota_daily is not None else 0)
    target.quota_monthly = d * 30
    target.name = f"{str(svc_name).upper()}-{d}/day"


@event.listens_for(Quota, "before_insert", propagate=True)
@event.listens_for(Quota, "before_update", propagate=True)
def _quota_before_save(mapper, connection, target: Quota) -> None:
    _quota_derive_name_and_monthly(connection, target)
