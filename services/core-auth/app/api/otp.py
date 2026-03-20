from fastapi import APIRouter, HTTPException, Request
from app.services.otp_service import generate_otp, store_otp, publish_otp_event
from app.services.verification_service import verify_otp
from app.services.rate_limiter import check_rate_limit

router = APIRouter()


@router.post("/send")
async def send_otp(request: Request, email: str):
    client_ip = request.client.host

    try:
        check_rate_limit(email)
        check_rate_limit(client_ip)
    except Exception as e:
        raise HTTPException(status_code=429, detail=str(e))

    otp = generate_otp()
    store_otp(email, otp)
    publish_otp_event(email, otp)

    # TEMP DEBUG: return OTP for local testing only
    return {"message": "OTP sent", "otp": otp}


@router.post("/verify")
async def verify(email: str, otp: str):
    try:
        valid = verify_otp(email, otp)
    except HTTPException as e:
        raise e

    if not valid:
        raise HTTPException(status_code=400, detail="Invalid OTP")

    return {"status": "verified"}

