"""Add email_logs.delivered for worker idempotency.

Revision ID: 002_email_logs_delivered
Revises: 001_initial_schema
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_email_logs_delivered"
down_revision: Union[str, Sequence[str], None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "email_logs",
        sa.Column(
            "delivered",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.create_index("ix_email_logs_delivered", "email_logs", ["delivered"])


def downgrade() -> None:
    op.drop_index("ix_email_logs_delivered", table_name="email_logs")
    op.drop_column("email_logs", "delivered")
