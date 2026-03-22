"""Add last_success_at, last_failure_at, updated_at to provider_health.

Revision ID: 005_ph_timestamps
Revises: 004_provider_health
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005_ph_timestamps"
down_revision: Union[str, Sequence[str], None] = "004_provider_health"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "provider_health",
        sa.Column(
            "last_success_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "provider_health",
        sa.Column(
            "last_failure_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.add_column(
        "provider_health",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("provider_health", "updated_at")
    op.drop_column("provider_health", "last_failure_at")
    op.drop_column("provider_health", "last_success_at")
