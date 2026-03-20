from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Body, Query
from pydantic import BaseModel, EmailStr, constr
import redis
from app.services.otp_service import generate_otp, store_otp, publish_otp_event
from app.services.verification_service import verify_otp
from app.services.rate_limiter import check_rate_limit
from app.services.usage_service import increment_usage

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
):
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
        check_rate_limit(email)
        check_rate_limit(client_ip)
    except Exception as e:
        raise HTTPException(status_code=429, detail=str(e))

    lock_key = f"otp:lock:{email}"
    if r.exists(lock_key):
        raise HTTPException(status_code=429, detail="OTP already sent recently")
    r.setex(lock_key, 60, "1")

    otp = generate_otp()
    store_otp(email, otp)
    publish_otp_event(email, otp)

    client = getattr(request.state, "client", None)
    if client and client.get("id"):
        increment_usage(str(client["id"]))

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

