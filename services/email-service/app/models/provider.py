"""
Registry for outbound email delivery. The worker loads rows by ``services.name`` and fails over in ``priority`` order.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class DeliveryProvider(Base):
    """
    Outbound backend for a channel. ``service`` = ``services.name`` (e.g. ``email``).

    Lower ``priority`` is tried first. ``provider_kind`` selects implementation; ``config`` overrides env SMTP.
    """

    __tablename__ = "email_delivery_providers"
    __table_args__ = (
        UniqueConstraint("service", "name", name="uq_email_delivery_providers_service_name"),
    )

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
