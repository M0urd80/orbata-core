"""initial schema

Revision ID: 001_initial_schema
Revises:
Create Date: 2025-03-20

All core-auth tables + ``email_delivery_providers`` (shared with email worker).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001_initial_schema"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "services",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "plans",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("price", sa.Float(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "quotas",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "name",
            sa.String(length=255),
            server_default=sa.text("''"),
            nullable=False,
        ),
        sa.Column(
            "quota_daily",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "quota_monthly",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quotas_service_id", "quotas", ["service_id"])

    op.create_table(
        "plan_quotas",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quota_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["quota_id"],
            ["quotas.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "plan_id",
            "quota_id",
            name="uq_plan_quota_plan_quota_id",
        ),
    )
    op.create_index("ix_plan_quotas_plan_id", "plan_quotas", ["plan_id"])
    op.create_index("ix_plan_quotas_quota_id", "plan_quotas", ["quota_id"])

    op.create_table(
        "clients",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("email_from_name", sa.String(length=255), nullable=True),
        sa.Column("api_key", sa.String(length=255), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["plans.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("api_key", name="uq_clients_api_key"),
    )
    op.create_index("ix_clients_plan_id", "clients", ["plan_id"])

    op.create_table(
        "email_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column(
            "attempts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_logs_client_id", "email_logs", ["client_id"])

    op.create_table(
        "usage",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "sent_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "success_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column(
            "fail_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["services.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "client_id",
            "date",
            "service_id",
            name="uq_usage_client_date_service_id",
        ),
    )
    op.create_index("ix_usage_client_id", "usage", ["client_id"])
    op.create_index("ix_usage_date", "usage", ["date"])
    op.create_index("ix_usage_service_id", "usage", ["service_id"])

    op.create_table(
        "email_delivery_providers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("service", sa.String(length=64), nullable=False),
        sa.Column("priority", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "provider_kind",
            sa.String(length=64),
            server_default=sa.text("'smtp'"),
            nullable=False,
        ),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_email_delivery_providers_service",
        "email_delivery_providers",
        ["service"],
    )
    op.create_index(
        "ix_email_delivery_providers_service_active_priority",
        "email_delivery_providers",
        ["service", "is_active", "priority"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_email_delivery_providers_service_active_priority",
        table_name="email_delivery_providers",
    )
    op.drop_index(
        "ix_email_delivery_providers_service",
        table_name="email_delivery_providers",
    )
    op.drop_table("email_delivery_providers")

    op.drop_index("ix_usage_service_id", table_name="usage")
    op.drop_index("ix_usage_date", table_name="usage")
    op.drop_index("ix_usage_client_id", table_name="usage")
    op.drop_table("usage")

    op.drop_index("ix_email_logs_client_id", table_name="email_logs")
    op.drop_table("email_logs")

    op.drop_index("ix_clients_plan_id", table_name="clients")
    op.drop_table("clients")

    op.drop_index("ix_plan_quotas_quota_id", table_name="plan_quotas")
    op.drop_index("ix_plan_quotas_plan_id", table_name="plan_quotas")
    op.drop_table("plan_quotas")

    op.drop_index("ix_quotas_service_id", table_name="quotas")
    op.drop_table("quotas")

    op.drop_table("plans")
    op.drop_table("services")
