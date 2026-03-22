from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.orm_base import Base


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    price: Mapped[float] = mapped_column(
        Float(asdecimal=False),
        nullable=False,
        default=0.0,
        server_default=text("0"),
    )
    # ORM default for API-created rows; server_default for AdminJS / raw SQL INSERTs.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=datetime.utcnow,
        server_default=text("now()"),
    )

    clients: Mapped[list["Client"]] = relationship("Client", back_populates="plan")
    plan_quotas: Mapped[list["PlanQuota"]] = relationship(
        "PlanQuota",
        back_populates="plan",
        cascade="all, delete-orphan",
    )
