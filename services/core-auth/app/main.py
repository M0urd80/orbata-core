from fastapi import FastAPI
from app.api.otp import router as otp_router

app = FastAPI(title="Orbata Core")

app.include_router(otp_router, prefix="/otp")


@app.get("/")
def root():
    return {"status": "Orbata Core Running"}

