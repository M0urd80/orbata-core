"""Default plan name for clients created without an explicit ``plan_id``."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.client import Client
from app.models.plan import Plan

DEFAULT_PLAN_NAME = "Free"


def get_plan_by_name(db: Session, name: str) -> Plan | None:
    return db.execute(select(Plan).where(Plan.name == name)).scalars().first()


def resolve_plan_id_for_new_client(db: Session, plan_id: uuid.UUID | None) -> uuid.UUID:
    """
    New clients always get a concrete ``plan_id``:

    - If ``plan_id`` is provided, validate it exists and return it.
    - Otherwise fetch the plan named **Free** and return ``Free.id``.
    """
    if plan_id is not None:
        if db.get(Plan, plan_id) is None:
            raise ValueError("Invalid plan_id")
        return plan_id
    free = get_plan_by_name(db, DEFAULT_PLAN_NAME)
    if free is None:
        raise ValueError(
            f'No plan_id provided and no plan named "{DEFAULT_PLAN_NAME}" exists. '
            "Create a Free plan or pass plan_id."
        )
    return free.id


def ensure_client_plan_or_assign_free(db: Session, client: Client) -> None:
    """
    Ensure ``client.plan_id`` points at an existing plan; otherwise assign the plan named **Free**.
    Raises ``ValueError`` (HTTP 503) if Free is missing.
    """
    plan_ok = client.plan_id is not None and db.get(Plan, client.plan_id) is not None
    if plan_ok:
        return
    free = get_plan_by_name(db, DEFAULT_PLAN_NAME)
    if free is None:
        raise ValueError(
            f'Client needs a default plan and "{DEFAULT_PLAN_NAME}" does not exist'
        )
    client.plan_id = free.id
    db.add(client)
    db.commit()
    db.refresh(client)
