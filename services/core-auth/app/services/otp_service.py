import json
import logging
import random
import redis

from app.core.config import OTP_TTL
from app.core.security import hash_otp

r = redis.Redis(host="redis", port=6379, decode_responses=True)
logger = logging.getLogger(__name__)

_ALLOWED_OTP_CHANNELS = frozenset({"sms", "whatsapp", "email"})


def _normalize_otp_queue_channel(channel: str) -> str:
    ch = str(channel).strip().lower()
    if ch not in _ALLOWED_OTP_CHANNELS:
        raise ValueError("Invalid channel")
    return ch


def generate_otp():
    return str(random.randint(100000, 999999))


def acquire_otp_lock(identifier: str, ttl: int = 60) -> bool:
    return bool(r.set(f"otp:lock:{identifier}", "1", ex=ttl, nx=True))


def store_otp(identifier: str, otp: str):
    hashed = hash_otp(otp)
    r.setex(f"otp:{identifier}", OTP_TTL, hashed)


def publish_otp_event(
    email: str,
    otp: str,
    client_name: str,
    client_id: str,
    log_id: str,
    service_id: str,
):
    channel = _normalize_otp_queue_channel("email")
    service = channel
    event = {
        "type": "OTP",
        "channel": channel,
        "service": service,
        "service_name": service,
        "to": email,
        "otp": otp,
        "client_id": client_id,
        "client_name": client_name,
        "log_id": log_id,
        "service_id": service_id,
        "attempt": 0,
        "max_attempts": 3,
        "next_try_at": 0,
    }
    r.lpush("email_queue", json.dumps(event))
    logger.info("📤 %s OTP event pushed to queue", channel.upper())


def publish_phone_otp_event(
    to: str,
    message: str,
    client_name: str,
    client_id: str,
    log_id: str,
    service_id: str,
    *,
    channel: str,
):
    """Queue SMS or WhatsApp OTP for the worker. ``channel`` must be ``sms`` or ``whatsapp`` (caller sets it; no phone-inference here)."""
    ch = _normalize_otp_queue_channel(channel)
    service = ch
    event = {
        "type": "OTP",
        "channel": ch,
        "service": service,
        "service_name": service,
        "to": to,
        "message": message,
        "client_id": client_id,
        "client_name": client_name,
        "log_id": log_id,
        "service_id": service_id,
        "attempt": 0,
        "max_attempts": 3,
        "next_try_at": 0,
    }
    r.lpush("email_queue", json.dumps(event))
    logger.info("📤 %s OTP event pushed to queue", ch.upper())


def publish_sms_otp_event(
    to: str,
    message: str,
    client_name: str,
    client_id: str,
    log_id: str,
    service_id: str,
):
    """Backward-compatible alias for ``channel=sms``."""
    publish_phone_otp_event(
        to,
        message,
        client_name,
        client_id,
        log_id,
        service_id,
        channel="sms",
    )

