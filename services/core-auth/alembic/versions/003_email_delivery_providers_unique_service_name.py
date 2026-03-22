"""Unique (service, name) on email_delivery_providers.

Revision ID: 003_edp_unique
Revises: 002_email_logs_delivered
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "003_edp_unique"
down_revision: Union[str, Sequence[str], None] = "002_email_logs_delivered"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_email_delivery_providers_service_name",
        "email_delivery_providers",
        ["service", "name"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_email_delivery_providers_service_name",
        "email_delivery_providers",
        type_="unique",
    )
