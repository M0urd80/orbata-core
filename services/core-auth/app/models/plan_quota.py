from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, UniqueConstraint, event, func, select
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.orm_base import Base


class PlanQuota(Base):
    """Link table: plan (package) → reusable ``Quota`` row."""

    __tablename__ = "plan_quotas"
    __table_args__ = (
        UniqueConstraint(
            "plan_id",
            "quota_id",
            name="uq_plan_quota_plan_quota_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    quota_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("quotas.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    plan: Mapped["Plan"] = relationship("Plan", back_populates="plan_quotas")
    quota_row: Mapped["Quota"] = relationship(
        "Quota", back_populates="plan_links"
    )


@event.listens_for(PlanQuota, "before_delete", propagate=True)
def _package_must_keep_one_quota(mapper, connection, target: PlanQuota) -> None:
    """
    Application rule: a package (plan) must keep ≥ 1 plan-quota link.
    """
    tbl = mapper.local_table
    q = select(func.count()).select_from(tbl).where(tbl.c.plan_id == target.plan_id)
    n = connection.execute(q).scalar_one()
    if n <= 1:
        raise ValueError(
            "Each package must have at least one quota. "
            "Add another link before removing this one."
        )
