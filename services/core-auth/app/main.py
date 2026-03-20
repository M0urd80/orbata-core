from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.api.otp import router as otp_router

app = FastAPI(title="Orbata Core")

app.include_router(otp_router, prefix="/otp")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"detail": "Invalid request payload"})


@app.get("/")
def root():
    return {"status": "Orbata Core Running"}

