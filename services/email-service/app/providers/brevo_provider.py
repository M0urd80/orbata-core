from __future__ import annotations

import logging
import os
import smtplib
from email.mime.text import MIMEText
from typing import Any

from app.providers.email_provider import EmailProvider

logger = logging.getLogger("email-worker.brevo")


class BrevoProvider(EmailProvider):
    """
    SMTP delivery (e.g. Brevo). Credentials from optional per-row ``config`` JSON or process env.

    ``config`` keys (all optional): ``smtp_host``, ``smtp_port``, ``smtp_login``,
    ``smtp_password``, ``from_email``.
    """

    def __init__(
        self,
        smtp_config: dict[str, Any] | None = None,
        *,
        label: str = "smtp",
    ) -> None:
        self._label = label
        cfg = smtp_config if isinstance(smtp_config, dict) else {}
        self._smtp_server = cfg.get("smtp_host") or os.getenv("SMTP_SERVER")
        port_raw = cfg.get("smtp_port")
        if port_raw is not None and str(port_raw).strip() != "":
            self._smtp_port = int(port_raw)
        else:
            self._smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self._smtp_login = cfg.get("smtp_login") or os.getenv("SMTP_LOGIN")
        self._smtp_password = cfg.get("smtp_password") or os.getenv("SMTP_PASSWORD")
        self._from_email = cfg.get("from_email") or os.getenv("FROM_EMAIL")
        self._conn: smtplib.SMTP | None = None

    def _get_connection(self) -> smtplib.SMTP:
        if self._conn is None:
            if not self._smtp_server:
                raise RuntimeError(
                    f"SMTP host missing for provider {self._label!r} "
                    "(set smtp_host in DB config or SMTP_SERVER env)"
                )
            conn = smtplib.SMTP(self._smtp_server, self._smtp_port, timeout=10)
            conn.starttls()
            conn.login(self._smtp_login, self._smtp_password)
            self._conn = conn
            logger.info("smtp_connected")
        return self._conn

    def _reset_connection(self) -> None:
        if self._conn is not None:
            try:
                self._conn.quit()
            except Exception:
                pass
            self._conn = None

    def send(self, payload: dict[str, Any]) -> None:
        to_email = payload["to"]
        otp = payload["otp"]
        client_name = payload.get("client_name") or "Orbata"
        subject = payload.get("subject") or "Your verification code"

        body = f"Your {client_name} verification code is: {otp}"
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = self._from_email
        msg["To"] = to_email

        try:
            conn = self._get_connection()
            conn.send_message(msg)
        except Exception:
            logger.warning(
                "smtp_failed_reconnecting",
                extra={"email": to_email, "provider": self._label},
            )
            self._reset_connection()
            conn = self._get_connection()
            conn.send_message(msg)
