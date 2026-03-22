from __future__ import annotations

import json
import logging
import os
from typing import Any

from twilio.rest import Client

from app.providers.base import BaseProvider

logger = logging.getLogger("email-worker.twilio")


class TwilioProvider(BaseProvider):
    """
    SMS / WhatsApp via Twilio. **Fully DB-configured for ``from_number``** (no env fallback).

    Payload::

        { "to": str, "message": str, "service": str (or "channel") }

    - **sms**: ``to`` must be E.164 (no ``whatsapp:`` prefix).
    - **whatsapp**: ``to`` must start with ``whatsapp:`` (caller formats; this class does not modify ``to``).

    ``account_sid`` / ``auth_token`` may come from config or env (warning logged if env).
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        label: str = "twilio",
    ) -> None:
        self._label = label
        self._config: dict[str, Any] = dict(config) if isinstance(config, dict) else {}

        sid = self._config.get("account_sid")
        if not sid:
            sid = os.getenv("TWILIO_ACCOUNT_SID")
            if sid:
                logger.warning(
                    "Twilio account_sid for %r loaded from TWILIO_ACCOUNT_SID env (prefer DB config)",
                    self._label,
                )
        token = self._config.get("auth_token")
        if not token:
            token = os.getenv("TWILIO_AUTH_TOKEN")
            if token:
                logger.warning(
                    "Twilio auth_token for %r loaded from TWILIO_AUTH_TOKEN env (prefer DB config)",
                    self._label,
                )
        if not sid or not token:
            raise RuntimeError(
                f"Twilio credentials missing for {self._label!r} "
                "(set account_sid/auth_token in DB config or TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN)"
            )
        self._client = Client(sid, token)

        fn = self._config.get("from_number")
        if not fn or not str(fn).strip():
            raise ValueError(
                f"from_number is required for TwilioProvider {self._label!r} (set in DB config JSON)"
            )
        self._from_number_value = str(fn).strip()

    def send(self, payload: dict[str, Any]) -> None:
        service = (
            str(payload.get("service") or payload.get("channel") or "")
            .strip()
            .lower()
        )
        to_addr = str(payload["to"]).strip()
        message = payload["message"]

        if service == "whatsapp":
            if not to_addr.lower().startswith("whatsapp:"):
                raise ValueError(
                    "WhatsApp requires 'to' with 'whatsapp:' prefix (e.g. whatsapp:+21658767023)"
                )
        elif service == "sms":
            if to_addr.lower().startswith("whatsapp:"):
                raise ValueError(
                    "SMS service requires E.164 'to' without 'whatsapp:' prefix"
                )

        from_number = self._from_number_value
        logger.info(
            "%s",
            json.dumps(
                {
                    "event": "twilio_send",
                    "provider": self._label,
                    "service": service or "unknown",
                    "from": from_number,
                    "to": to_addr,
                }
            ),
        )
        msg = self._client.messages.create(
            body=str(message),
            from_=from_number,
            to=to_addr,
        )
        logger.info(
            "twilio_message_sent",
            extra={"provider": self._label, "sid": getattr(msg, "sid", None)},
        )
