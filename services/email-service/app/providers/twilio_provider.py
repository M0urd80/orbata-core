from __future__ import annotations

import logging
import os
from typing import Any

from twilio.rest import Client

from app.providers.base import BaseProvider

logger = logging.getLogger("email-worker.twilio")


class TwilioProvider(BaseProvider):
    """
    SMS / WhatsApp via ``twilio.rest.Client``. Payload::

        { "to": str, "message": str, "service": str, "channel": str }

    When ``service`` / ``channel`` is ``whatsapp``, ``to`` is forced to ``whatsapp:+E164``
    (Twilio otherwise treats a bare E.164 as SMS). Logs ``To=whatsapp:+...`` before ``create``.

    ``from_`` comes from merged config key ``from_number`` (DB JSON) or ``TWILIO_PHONE_NUMBER`` env.
    """

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        label: str = "twilio",
    ) -> None:
        self._label = label
        self._config: dict[str, Any] = dict(config) if isinstance(config, dict) else {}
        sid = self._config.get("account_sid") or os.getenv("TWILIO_ACCOUNT_SID")
        token = self._config.get("auth_token") or os.getenv("TWILIO_AUTH_TOKEN")
        if not sid or not token:
            raise RuntimeError(
                f"Twilio credentials missing for {self._label!r} "
                "(config account_sid/auth_token or TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN)"
            )
        self._client = Client(sid, token)

    def _from_number(self) -> str:
        fn = (
            self._config.get("from_number")
            or self._config.get("phone_number")
            or os.getenv("TWILIO_PHONE_NUMBER")
        )
        if not fn:
            raise RuntimeError(
                f"from_number missing for {self._label!r} "
                "(set in provider config JSON or TWILIO_PHONE_NUMBER)"
            )
        return str(fn)

    def send(self, payload: dict[str, Any]) -> None:
        service = (
            str(payload.get("service") or payload.get("channel") or "")
            .strip()
            .lower()
        )
        to_raw = str(payload["to"]).strip()
        if service == "whatsapp":
            if to_raw.lower().startswith("whatsapp:"):
                to_addr = to_raw
            else:
                clean = to_raw.replace(" ", "").replace("-", "")
                to_addr = f"whatsapp:{clean}"
        elif to_raw.lower().startswith("whatsapp:"):
            to_addr = to_raw
        else:
            to_addr = to_raw.replace(" ", "").replace("-", "")
        message = payload["message"]
        from_number = self._from_number()
        logger.info(
            "Twilio messages.create To=%s (service=%s)",
            to_addr,
            service or "sms",
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
