"""Maps to core-auth `usage` table (daily aggregates per client/channel)."""

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def utc_today() -> date:
    return datetime.now(timezone.utc).date()


class Usage(Base):
    __tablename__ = "usage"
    __table_args__ = (
        UniqueConstraint(
            "client_id",
            "date",
            "channel",
            name="uq_usage_client_date_channel",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="email")
    sent_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fail_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
