from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Body, Query, Depends
from pydantic import BaseModel, EmailStr, constr
from sqlalchemy.orm import Session
import redis
from app.core.database import get_db
from app.services.otp_service import generate_otp, store_otp
from app.services.email_log_service import create_pending_log_and_enqueue
from app.services.verification_service import verify_otp
from app.services.rate_limiter import check_rate_limit as check_email_ip_rate_limit
from app.services.rate_limit_service import check_rate_limit as check_client_rate_limit
from app.services.usage_service import increment_sent

router = APIRouter()
r = redis.Redis(host="redis", port=6379, decode_responses=True)


class SendOTPRequest(BaseModel):
    email: EmailStr


class VerifyOTPRequest(BaseModel):
    email: EmailStr
    otp: constr(min_length=6, max_length=6, pattern=r"^[0-9]+$")


@router.post("/send")
async def send_otp(
    request: Request,
    data: Optional[SendOTPRequest] = Body(default=None),
    email: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    client_ctx = getattr(request.state, "client", None)
    if not client_ctx or not client_ctx.get("id"):
        raise HTTPException(status_code=401, detail="Invalid client context")
    check_client_rate_limit(str(client_ctx["id"]))

    raw_email = str(data.email) if data and data.email else email
    if not raw_email:
        raise HTTPException(status_code=400, detail="Email is required")

    try:
        validated = SendOTPRequest(email=raw_email)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid email format")

    email = str(validated.email)
    client_ip = request.client.host

    try:
        check_email_ip_rate_limit(email)
        check_email_ip_rate_limit(client_ip)
    except Exception as e:
        raise HTTPException(status_code=429, detail=str(e))

    lock_key = f"otp:lock:{email}"
    if r.exists(lock_key):
        raise HTTPException(status_code=429, detail="OTP already sent recently")
    r.setex(lock_key, 60, "1")

    otp = generate_otp()
    store_otp(email, otp)
    client_name = client_ctx.get("email_from_name") or client_ctx["name"]
    create_pending_log_and_enqueue(
        db,
        recipient_email=email,
        client_id=str(client_ctx["id"]),
        otp=otp,
        client_name=client_name,
    )

    increment_sent(db, str(client_ctx["id"]))

    # TEMP DEBUG: return OTP for local testing only
    return {"message": "OTP sent", "otp": otp}


@router.post("/verify")
async def verify(
    data: Optional[VerifyOTPRequest] = Body(default=None),
    email: Optional[str] = Query(default=None),
    otp: Optional[str] = Query(default=None),
):
    raw_email = str(data.email) if data and data.email else email
    raw_otp = data.otp if data and data.otp else otp
    if not raw_email or not raw_otp:
        raise HTTPException(status_code=400, detail="Email and OTP are required")

    try:
        validated = VerifyOTPRequest(email=raw_email, otp=raw_otp)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid email or OTP format")

    try:
        valid = verify_otp(str(validated.email), validated.otp)
    except HTTPException as e:
        raise e

    if not valid:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    return {"status": "verified"}

