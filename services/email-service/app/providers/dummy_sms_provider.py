from __future__ import annotations

import logging
from typing import Any

from app.providers.base import BaseProvider

logger = logging.getLogger("email-worker.dummy_sms")


class DummySMSProvider(BaseProvider):
    """
    No-op SMS provider for dev / failover testing.

    Never raises; logs payload and returns (``BaseProvider.send`` → ``None``).
    """

    def __init__(self, *, label: str = "dummy") -> None:
        self._label = label

    def send(self, payload: dict[str, Any]) -> None:
        to = payload.get("to", "")
        message = payload.get("message", "")
        line = f"📱 Dummy SMS [{self._label}] to={to!r} message={message!r}"
        print(line, flush=True)
        logger.info("dummy_sms_sent", extra={"to": to, "provider": self._label})
