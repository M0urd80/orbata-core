"""
Load ``email_delivery_providers`` rows for a channel and send with failover.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import and_, exists, select
from sqlalchemy.orm import Session

from app.models.provider import DeliveryProvider
from app.models.provider_health import ProviderHealth
from app.services.provider_health import record_failure, record_success
from app.providers.base import BaseProvider
from app.providers.errors import ProviderError
from app.providers.factory import build_provider_from_kind
from usage_model import Service

logger = logging.getLogger("email-worker.routing")

SERVICE_NAME_EMAIL = "email"
SERVICE_NAME_SMS = "sms"
SERVICE_NAME_WHATSAPP = "whatsapp"

# Cross-channel failover: if every provider for the first service fails, try the next.
FALLBACK_CHAIN: dict[str, list[str]] = {
    SERVICE_NAME_WHATSAPP: [SERVICE_NAME_WHATSAPP, SERVICE_NAME_SMS, SERVICE_NAME_EMAIL],
    SERVICE_NAME_SMS: [SERVICE_NAME_SMS, SERVICE_NAME_WHATSAPP, SERVICE_NAME_EMAIL],
    SERVICE_NAME_EMAIL: [SERVICE_NAME_EMAIL],
}


def _fallback_services(requested: str) -> list[str]:
    key = str(requested).strip().lower()
    chain = FALLBACK_CHAIN.get(key)
    if chain is not None:
        return list(chain)
    return [key]


def _payload_for_service(
    svc: str,
    payload: dict[str, Any],
    job: dict[str, Any] | None,
) -> dict[str, Any]:
    """Copy payload and set channel/service; enrich email sends when falling back from SMS/WA."""
    out: dict[str, Any] = {**payload}
    svc_norm = str(svc).strip().lower()
    out["channel"] = svc_norm
    out["service"] = svc_norm
    # Twilio SMS expects E.164 (+...), not whatsapp:+... (WA addressing).
    if svc_norm == SERVICE_NAME_SMS:
        raw_to = out.get("to")
        if isinstance(raw_to, str):
            prefix = "whatsapp:"
            if raw_to.lower().startswith(prefix):
                out["to"] = raw_to[len(prefix) :].lstrip()
    if svc_norm == SERVICE_NAME_EMAIL and job is not None:
        if out.get("otp") is None and job.get("otp") is not None:
            out["otp"] = job["otp"]
        if not out.get("client_name") and job.get("client_name"):
            out["client_name"] = job["client_name"]
        if not out.get("to"):
            out["to"] = job.get("email") or job.get("to")
    return out


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
    """
    Active delivery providers for one channel.

    **Lookup is only on** ``email_delivery_providers.service`` **(string equality)** —
    there is **no** join to ``services`` and **no** ``service_id`` on this table.

    Equivalent SQL (plus optional ``NOT EXISTS`` for ``provider_health``)::

        SELECT * FROM email_delivery_providers
        WHERE service = :service_name
          AND is_active = true
        ORDER BY priority ASC, name ASC;

    ``service_name`` is normalized with ``strip().lower()`` so it matches seeded values
    (``sms``, ``whatsapp``, ``email``).
    """
    service = str(service_name).strip().lower()
    logger.info(f"DEBUG → querying providers for service='{service}'")
    disabled_health = exists().where(
        and_(
            ProviderHealth.provider_name == DeliveryProvider.name,
            ProviderHealth.service == DeliveryProvider.service,
            ProviderHealth.disabled.is_(True),
        )
    )
    rows = list(
        db.execute(
            select(DeliveryProvider)
            .where(
                DeliveryProvider.service == service,
                DeliveryProvider.is_active.is_(True),
                ~disabled_health,
            )
            .order_by(DeliveryProvider.priority.asc(), DeliveryProvider.name.asc())
        )
        .scalars()
        .all()
    )
    logger.info(f"DEBUG → providers found: {len(rows)}")
    return rows


def build_provider_from_row(row: DeliveryProvider) -> BaseProvider:
    cfg = row.config if isinstance(row.config, dict) else None
    return build_provider_from_kind(
        row.provider_kind, name=row.name, config=cfg
    )


def _log_provider_selected(row: DeliveryProvider, service_name: str) -> None:
    """Structured log: which DB row is used and configured sender (if any)."""
    cfg = row.config if isinstance(row.config, dict) else {}
    from_addr = (
        cfg.get("from_number")
        or cfg.get("from_email")
        or cfg.get("phone_number")
    )
    logger.info(
        "%s",
        json.dumps(
            {
                "event": "provider_selected",
                "provider": row.name,
                "service": service_name,
                "from": from_addr,
                "provider_kind": row.provider_kind,
                "priority": row.priority,
            },
            default=str,
        ),
    )


def send_with_failover(
    db: Session,
    service_name: str,
    payload: dict[str, Any],
    job: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """
    Try providers in :data:`FALLBACK_CHAIN` order (cross-channel failover).

    For each service in the chain, load active rows from ``email_delivery_providers`` and
    try in priority order until one succeeds.

    Returns ``(provider_used_label, "db")``. Routing is DB-only (no env fallback).

    Raises :class:`RuntimeError` if there are no active providers for **any** service in the chain.
    Raises :class:`ProviderError` if every configured provider fails (worker may retry that only).

    Provider rows are chosen only by the string ``email_delivery_providers.service`` (see
    :func:`fetch_active_providers_for_service`), not by ``service_id`` joins.
    """
    requested = str(service_name).strip().lower()
    chain = _fallback_services(requested)
    logger.info("🔁 Routing start → requested=%s, fallback_chain=%s", requested, chain)

    errors: list[str] = []
    last_exc: BaseException | None = None
    saw_any_provider = False
    total_attempts = 0

    def _safe_record_success(provider_name: str, health_service: str) -> None:
        try:
            health = record_success(db, provider_name, health_service)
            logger.info(
                "📊 Provider health → %s: success=%s, fail=%s, disabled=%s",
                provider_name,
                health.success_count,
                health.failure_count,
                health.disabled,
            )
        except Exception as db_err:
            logger.error(
                "⚠️ health update failed BUT delivery succeeded (provider=%s): %s",
                provider_name,
                db_err,
            )

    def _safe_record_failure(provider_name: str, health_service: str) -> None:
        try:
            health = record_failure(db, provider_name, health_service)
            logger.info(
                "📊 Provider health → %s: success=%s, fail=%s, disabled=%s",
                provider_name,
                health.success_count,
                health.failure_count,
                health.disabled,
            )
        except Exception as db_err:
            logger.error(
                "⚠️ health failure record failed (provider=%s): %s",
                provider_name,
                db_err,
            )

    for i, svc in enumerate(chain):
        if i > 0:
            logger.info("🔁 Switching fallback → %s", svc)
        rows = fetch_active_providers_for_service(db, svc)
        if not rows:
            logger.info(
                "No active providers for fallback service=%r — trying next in chain",
                svc,
            )
            continue
        saw_any_provider = True
        send_payload = _payload_for_service(svc, payload, job)
        health_service = str(svc).strip().lower()

        for row in rows:
            total_attempts += 1
            logger.info(
                "➡️ Trying provider: %s (priority=%s) service=%s",
                row.name,
                row.priority,
                health_service,
            )
            _log_provider_selected(row, health_service)
            send_ok = False
            try:
                provider = build_provider_from_row(row)
                provider.send(send_payload)
                send_ok = True
            except Exception as e:
                last_exc = e
                msg = f"{health_service}/{row.name}: {e}"
                errors.append(msg)
                _safe_record_failure(row.name, health_service)
                logger.error("❌ Failed provider %s: %s", row.name, str(e))
                logger.warning(
                    "delivery_provider_failed",
                    extra={
                        "provider": row.name,
                        "service": health_service,
                        "error": str(e),
                    },
                )
                continue

            if send_ok:
                _safe_record_success(row.name, health_service)
                logger.info("✅ Success via %s (service=%s)", row.name, health_service)
                logger.info(
                    "🏁 Delivery completed → provider=%s, attempts=%s",
                    row.name,
                    total_attempts,
                )
                return row.name, "db"

    if not saw_any_provider:
        raise RuntimeError(
            "No active providers for any service in fallback chain %r — add rows to "
            "email_delivery_providers" % (chain,)
        )

    logger.info(
        "🏁 Delivery completed → provider=None, attempts=%s (all failed)",
        total_attempts,
    )
    raise ProviderError(
        "All delivery providers failed for requested=%r (chain=%r): %s"
        % (requested, chain, "; ".join(errors))
    ) from last_exc
