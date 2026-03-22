import logging
import re
from typing import Literal, Optional

import redis
from fastapi import APIRouter, HTTPException, Request, Body, Query, Depends
from pydantic import BaseModel, EmailStr, Field, TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.core.config import REDIS_HOST
from app.core.database import get_db
from app.services.api_key_service import ClientAuthError, require_client_from_api_key_header
from app.services.email_log_service import (
    create_pending_log_and_enqueue,
    create_pending_sms_log_and_enqueue,
)
from app.services.otp_service import generate_otp, store_otp
from app.services.rate_limiter import check_rate_limit as check_email_ip_rate_limit
from app.services.rate_limit_service import check_rate_limit as check_client_rate_limit
from app.services.usage_service import (
    SERVICE_NAME,
    SERVICE_NAME_SMS,
    SERVICE_NAME_WHATSAPP,
    check_quota,
    get_quota_for_plan_and_service,
    get_service,
    increment_usage,
)
from app.services.plan_defaults import ensure_client_plan_or_assign_free
from app.services.verification_service import verify_otp

router = APIRouter()
r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)
logger = logging.getLogger(__name__)

# E.164: +[country][number] — 8–15 digits after '+' (first digit 1–9, then 7–14 more).
E164_REGEX = re.compile(r"^\+[1-9]\d{7,14}$")
_ALLOWED_CHANNELS = frozenset({"email", "sms", "whatsapp"})
_email_adapter = TypeAdapter(EmailStr)


def normalize_phone(phone: str) -> str:
    return str(phone).strip().replace(" ", "").replace("-", "")


def is_valid_phone(phone: str) -> bool:
    normalized = normalize_phone(phone)
    return bool(E164_REGEX.match(normalized))


def normalize_e164_phone(raw: str | None) -> Optional[str]:
    """
    Normalize then match ``E164_REGEX``. Call only when channel is **sms** or **whatsapp**.
    Strips optional ``whatsapp:`` prefix (verify/send may use ``whatsapp:+E164``).
    Rejects local numbers (e.g. 058767023) and missing ``+`` (e.g. 21658767023).
    """
    if raw is None or not str(raw).strip():
        return None
    phone = normalize_phone(str(raw))
    low = phone.lower()
    if low.startswith("whatsapp:"):
        phone = normalize_phone(phone[9:])
    if E164_REGEX.match(phone):
        return phone
    return None


def _pick_query_param(
    request: Request,
    body_val: Optional[str],
    query_dep: Optional[str],
    name: str,
) -> Optional[str]:
    """
    Prefer JSON body, then FastAPI ``Query(...)``, then raw ``request.query_params.get(name)``.
    Ensures ``?to=...`` is never dropped in favor of only ``sms`` (and survives odd proxy/query parsing).
    """
    for v in (body_val, query_dep, request.query_params.get(name)):
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return None


def parse_email_address(raw: str | None) -> Optional[str]:
    if raw is None or not str(raw).strip():
        return None
    try:
        return str(_email_adapter.validate_python(str(raw).strip()))
    except ValidationError:
        return None


def _validate_request_channel(channel_raw: Optional[str]) -> str:
    """
    Use the request channel as-is (default ``email`` only when absent).
    Never infer ``sms`` from phone-shaped ``to``.
    """
    ch = (channel_raw or "email").strip().lower()
    if ch not in _ALLOWED_CHANNELS:
        raise HTTPException(
            status_code=400,
            detail="channel must be one of: email, sms, whatsapp",
        )
    return ch


class SendOTPBody(BaseModel):
    """``channel`` defaults to ``email``. Use ``to`` as a single destination (email or E.164) for the active channel."""

    channel: Literal["email", "sms", "whatsapp"] = "email"
    email: Optional[EmailStr] = None
    sms: Optional[str] = Field(
        default=None,
        description="E.164 phone, e.g. +15551234567",
    )
    to: Optional[str] = Field(
        default=None,
        description="Destination: email if channel=email, else E.164",
    )


class VerifyOTPBody(BaseModel):
    channel: Literal["email", "sms", "whatsapp"] = "email"
    email: Optional[EmailStr] = None
    sms: Optional[str] = Field(default=None, description="E.164 phone")
    to: Optional[str] = None
    otp: str = Field(
        ...,
        min_length=6,
        max_length=6,
        pattern=r"^[0-9]+$",
    )


@router.post("/send")
async def send_otp(
    request: Request,
    data: Optional[SendOTPBody] = Body(default=None),
    channel: str = Query(
        "email",
        description="email (default) | sms | whatsapp",
    ),
    email: Optional[str] = Query(default=None),
    sms: Optional[str] = Query(default=None),
    to: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """
    Send OTP on **channel** (default **email**).

    - **email**: body/query ``email`` or ``to`` (validated email).
    - **sms**: body/query ``sms`` or ``to`` (E.164).
    - **whatsapp**: same as SMS; ``to`` is queued as ``whatsapp:+E164`` for Twilio.

    SMS quota uses ``services`` row **sms**; WhatsApp uses **whatsapp**.

    **Query strings:** a leading ``+`` in ``to`` / ``sms`` must be sent as ``%2B`` (e.g. ``?to=%2B21658767023``),
    otherwise ``+`` may decode as a space.

    **Channel is the only source of truth** (``email`` | ``sms`` | ``whatsapp``). It is never changed
    based on whether ``to`` looks like a phone number—set ``channel=whatsapp`` or ``channel=sms`` for E.164.
    """
    try:
        client = require_client_from_api_key_header(db, request)
    except ClientAuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail) from e

    client_id_str = str(client.id)
    check_client_rate_limit(client_id_str)

    ch_in = _pick_query_param(
        request,
        data.channel if data else None,
        channel,
        "channel",
    ) or "email"
    raw_to = _pick_query_param(
        request,
        data.to if data else None,
        to,
        "to",
    )
    raw_email = _pick_query_param(
        request,
        str(data.email) if data and data.email else None,
        email,
        "email",
    )
    raw_sms_in = _pick_query_param(
        request,
        data.sms if data else None,
        sms,
        "sms",
    )

    email_dest = raw_email or (parse_email_address(raw_to) if raw_to else None)
    has_email = bool(email_dest)

    ch = _validate_request_channel(ch_in)
    logger.info("🔥 REQUEST CHANNEL: %s", ch)

    if ch == "email":
        if not email_dest:
            raise HTTPException(
                status_code=400,
                detail="Provide a valid email (email=, to=, or JSON email/to)",
            )
        phone_dest = None
    else:
        phone_dest = normalize_e164_phone(raw_sms_in) or normalize_e164_phone(
            raw_to
        )
        if not phone_dest:
            raise HTTPException(
                status_code=400,
                detail="Provide a valid E.164 phone (sms=, to=, e.g. +21658767023)",
            )

    client_ip = request.client.host if request.client else ""

    try:
        ensure_client_plan_or_assign_free(db, client)
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    if ch == "email":
        return await _send_otp_email(
            db=db,
            client=client,
            client_id_str=client_id_str,
            email=email_dest,
            client_ip=client_ip,
            channel=ch,
        )

    return await _send_otp_sms(
        db=db,
        client=client,
        client_id_str=client_id_str,
        phone=phone_dest,
        client_ip=client_ip,
        logical_channel=ch,
    )


async def _send_otp_email(
    *,
    db: Session,
    client,
    client_id_str: str,
    email: str,
    client_ip: str,
    channel: str,
):
    try:
        check_email_ip_rate_limit(email)
        if client_ip:
            check_email_ip_rate_limit(client_ip)
    except Exception as e:
        raise HTTPException(status_code=429, detail=str(e))

    service = get_service(db, SERVICE_NAME)
    if not service:
        raise HTTPException(
            status_code=503,
            detail=f"Service '{SERVICE_NAME}' is not configured (seed services table)",
        )

    quota_row = get_quota_for_plan_and_service(db, client.plan_id, service.id)
    check_quota(db, client=client, service=service, quota=quota_row)

    lock_key = f"otp:lock:{email}"
    if r.exists(lock_key):
        raise HTTPException(status_code=429, detail="OTP already sent recently")
    r.setex(lock_key, 60, "1")

    otp = generate_otp()
    store_otp(email, otp)
    client_name = client.email_from_name or client.name

    create_pending_log_and_enqueue(
        db,
        recipient_email=email,
        client_id=client_id_str,
        otp=otp,
        client_name=client_name,
        service_id=str(service.id),
    )

    increment_usage(db, client_id_str, service_id=service.id)

    return {"message": "OTP sent", "channel": channel, "otp": otp}


async def _send_otp_sms(
    *,
    db: Session,
    client,
    client_id_str: str,
    phone: str,
    client_ip: str,
    logical_channel: Literal["sms", "whatsapp"] = "sms",
):
    try:
        check_email_ip_rate_limit(phone)
        if client_ip:
            check_email_ip_rate_limit(client_ip)
    except Exception as e:
        raise HTTPException(status_code=429, detail=str(e))

    service_name = (
        SERVICE_NAME_WHATSAPP if logical_channel == "whatsapp" else SERVICE_NAME_SMS
    )
    service = get_service(db, service_name)
    if not service:
        raise HTTPException(
            status_code=503,
            detail=f"Service '{service_name}' is not configured (seed services table)",
        )

    quota_row = get_quota_for_plan_and_service(db, client.plan_id, service.id)
    check_quota(db, client=client, service=service, quota=quota_row)

    lock_key = f"otp:lock:{logical_channel}:{phone}"
    if r.exists(lock_key):
        raise HTTPException(status_code=429, detail="OTP already sent recently")
    r.setex(lock_key, 60, "1")

    otp = generate_otp()
    store_otp(phone, otp)
    message = f"Your OTP is {otp}"

    delivery_to = (
        f"whatsapp:{phone}"
        if logical_channel == "whatsapp"
        else phone
    )

    create_pending_sms_log_and_enqueue(
        db,
        recipient_phone=delivery_to,
        client_id=client_id_str,
        message=message,
        client_name=client.email_from_name or client.name,
        service_id=str(service.id),
        queue_to=delivery_to,
        queue_channel=logical_channel,
    )

    increment_usage(db, client_id_str, service_id=service.id)

    return {"message": "OTP sent", "channel": logical_channel, "otp": otp}


@router.post("/verify")
async def verify(
    request: Request,
    data: Optional[VerifyOTPBody] = Body(default=None),
    channel: str = Query("email", description="email | sms | whatsapp"),
    email: Optional[str] = Query(default=None),
    sms: Optional[str] = Query(default=None),
    to: Optional[str] = Query(default=None),
    otp: Optional[str] = Query(default=None),
):
    ch_in = _pick_query_param(
        request,
        data.channel if data else None,
        channel,
        "channel",
    ) or "email"
    raw_to = _pick_query_param(
        request,
        data.to if data else None,
        to,
        "to",
    )
    raw_email = _pick_query_param(
        request,
        str(data.email) if data and data.email else None,
        email,
        "email",
    )
    raw_sms_in = _pick_query_param(
        request,
        data.sms if data else None,
        sms,
        "sms",
    )
    raw_otp = (data.otp if data and data.otp else None) or otp
    raw_otp = str(raw_otp).strip() if raw_otp is not None else None

    email_dest = raw_email or (parse_email_address(raw_to) if raw_to else None)
    has_email = bool(email_dest)

    ch = _validate_request_channel(ch_in)
    logger.info("🔥 REQUEST CHANNEL: %s", ch)

    if ch == "email":
        if not email_dest:
            raise HTTPException(
                status_code=400,
                detail="Provide email (or to=) and otp",
            )
        identifier = email_dest
    else:
        phone_dest = normalize_e164_phone(raw_sms_in) or normalize_e164_phone(
            raw_to
        )
        if not phone_dest:
            raise HTTPException(
                status_code=400,
                detail="Provide a valid E.164 phone (sms= or to=)",
            )
        identifier = phone_dest

    if not raw_otp:
        raise HTTPException(status_code=400, detail="OTP is required")

    try:
        valid = verify_otp(identifier, str(raw_otp))
    except HTTPException as e:
        raise e

    if not valid:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    return {"status": "verified"}
