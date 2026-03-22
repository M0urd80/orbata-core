"""
Outbound delivery registry (email/SMS routing in worker). Same table as email-service ORM.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.orm_base import Base


class EmailDeliveryProvider(Base):
    """Row in ``email_delivery_providers`` (worker failover by ``service`` + ``priority``)."""

    __tablename__ = "email_delivery_providers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    service: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    provider_kind: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="smtp",
        server_default=text("'smtp'"),
    )
    config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
