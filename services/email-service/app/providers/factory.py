from __future__ import annotations

from typing import Any

from app.providers.base import BaseProvider
from app.providers.brevo_provider import BrevoProvider
from app.providers.dummy_sms_provider import DummySMSProvider
from app.providers.twilio_provider import TwilioProvider


def build_provider_from_kind(
    provider_kind: str | None,
    *,
    name: str = "provider",
    config: dict[str, Any] | None = None,
) -> BaseProvider:
    """
    Map DB ``provider_kind`` to implementation.

    - ``smtp`` (and legacy ``smtp_env``, ``brevo``) → ``BrevoProvider``
    - ``twilio`` → ``TwilioProvider``
    - ``dummy`` → ``DummySMSProvider`` (log-only; use as SMS failover)
    """
    kind = (provider_kind or "smtp").strip().lower()
    cfg = config if isinstance(config, dict) else None
    if kind == "smtp" or kind in ("smtp_env", "brevo"):
        return BrevoProvider(smtp_config=cfg, label=name)
    if kind == "twilio":
        return TwilioProvider(config=cfg or {}, label=name)
    if kind == "dummy":
        return DummySMSProvider(label=name)
    raise ValueError(f"Unsupported provider_kind={provider_kind!r} for {name!r}")


def get_provider(service: str = "email") -> BaseProvider:
    """
    Single default provider from env (no DB). Prefer ``routing.send_with_failover`` in the worker.
    """
    if service == "email":
        return BrevoProvider(smtp_config=None, label="legacy_env")
    if service == "sms":
        return TwilioProvider(config={}, label="legacy_env")
    raise ValueError(f"No provider registered for service={service!r}")
