from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.orm_base import Base


def utc_today() -> date:
    """Calendar day in UTC (matches server-side billing boundaries)."""
    return datetime.now(timezone.utc).date()


class Usage(Base):
    """One aggregate row per client per UTC calendar day per service."""

    __tablename__ = "usage"
    __table_args__ = (
        UniqueConstraint(
            "client_id",
            "date",
            "service_id",
            name="uq_usage_client_date_service_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    service_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("services.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sent_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fail_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    service: Mapped["Service"] = relationship("Service", back_populates="usage_records")
