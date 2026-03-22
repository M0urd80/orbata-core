"""
Load ``email_delivery_providers`` rows for a channel and send with failover.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.provider import DeliveryProvider
from app.providers.base import BaseProvider
from app.providers.brevo_provider import BrevoProvider
from app.providers.factory import build_provider_from_kind
from app.providers.twilio_provider import TwilioProvider
from usage_model import Service

logger = logging.getLogger("email-worker.routing")

SERVICE_NAME_EMAIL = "email"
SERVICE_NAME_SMS = "sms"
SERVICE_NAME_WHATSAPP = "whatsapp"


def _lookup_service_name(db: Session, service_id_raw: Any) -> str:
    """Map ``service_id`` UUID → ``services.name``; default ``email`` (never ``sms``)."""
    try:
        sid = uuid.UUID(str(service_id_raw))
    except (ValueError, TypeError):
        return SERVICE_NAME_EMAIL
    row = db.execute(select(Service).where(Service.id == sid)).scalars().first()
    return row.name if row else SERVICE_NAME_EMAIL


def resolve_service_name(db: Session, job: dict[str, Any]) -> str:
    """
    Priority:
    1. ``job["channel"]`` (non-empty string)
    2. ``job["service_id"]`` → DB lookup
    3. ``"email"`` — never default to ``sms``.
    """
    if "channel" in job:
        raw = job["channel"]
        if raw is not None and str(raw).strip() != "":
            return str(raw).strip().lower()
    if "service_id" in job and job.get("service_id"):
        return _lookup_service_name(db, job["service_id"])
    return SERVICE_NAME_EMAIL


def resolve_channel_name(db: Session, job: dict[str, Any]) -> str:
    """
    Like ``resolve_service_name`` but also honors ``job["service"]`` when ``channel`` is absent.
    Order: ``channel`` → ``service`` → ``service_id`` → ``email``.
    """
    if "channel" in job:
        raw = job["channel"]
        if raw is not None and str(raw).strip() != "":
            return str(raw).strip().lower()
    if "service" in job:
        raw = job["service"]
        if raw is not None and str(raw).strip() != "":
            return str(raw).strip().lower()
    if "service_id" in job and job.get("service_id"):
        return _lookup_service_name(db, job["service_id"])
    return SERVICE_NAME_EMAIL


def fetch_active_providers_for_service(
    db: Session, service_name: str
) -> list[DeliveryProvider]:
    """Active rows for channel, lowest ``priority`` first."""
    return list(
        db.execute(
            select(DeliveryProvider)
            .where(
                DeliveryProvider.service == service_name,
                DeliveryProvider.is_active.is_(True),
            )
            .order_by(DeliveryProvider.priority.asc(), DeliveryProvider.name.asc())
        )
        .scalars()
        .all()
    )


def build_provider_from_row(row: DeliveryProvider) -> BaseProvider:
    cfg = row.config if isinstance(row.config, dict) else None
    return build_provider_from_kind(
        row.provider_kind, name=row.name, config=cfg
    )


def send_with_failover(
    db: Session,
    service_name: str,
    payload: dict[str, Any],
) -> tuple[str, str]:
    """
    Try each active provider in priority order until one succeeds.

    Returns ``(provider_used_label, mode)`` where mode is ``"db"`` or ``"env_fallback"``.

    Raises the last error if every attempt fails (worker maps to retry/DLQ).
    """
    rows = fetch_active_providers_for_service(db, service_name)
    errors: list[str] = []
    for row in rows:
        try:
            provider = build_provider_from_row(row)
            provider.send(payload)
            return row.name, "db"
        except Exception as e:
            msg = f"{row.name}: {e}"
            errors.append(msg)
            logger.warning(
                "delivery_provider_failed",
                extra={
                    "provider": row.name,
                    "service": service_name,
                    "error": str(e),
                },
            )

    if rows:
        raise RuntimeError(
            "All delivery providers failed for service=%r: %s"
            % (service_name, "; ".join(errors))
        )

    # No DB rows: env-only fallbacks (legacy)
    if service_name in (SERVICE_NAME_SMS, SERVICE_NAME_WHATSAPP):
        logger.info(
            "no_db_delivery_providers",
            extra={"service": service_name, "fallback": "env_twilio"},
        )
        TwilioProvider(label="env_twilio_fallback").send(payload)
        return "env_twilio_fallback", "env_fallback"

    logger.info(
        "no_db_delivery_providers",
        extra={"service": service_name, "fallback": "env_smtp"},
    )
    p = BrevoProvider(smtp_config=None, label="env_fallback")
    p.send(payload)
    return "env_fallback", "env_fallback"
