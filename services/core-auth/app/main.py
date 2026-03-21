from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.api.otp import router as otp_router
from app.api.admin import router as admin_router
from app.core.database import init_db_schema
from app.middleware.api_key_middleware import ApiKeyMiddleware
from app.models.client import Client  # noqa: F401
from app.models.email_log import EmailLog  # noqa: F401
from app.models.usage import Usage  # noqa: F401

app = FastAPI(title="Orbata Core")
app.add_middleware(ApiKeyMiddleware)

app.include_router(otp_router, prefix="/otp")
app.include_router(admin_router, prefix="/admin")


@app.on_event("startup")
def on_startup():
    init_db_schema()


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=400, content={"detail": "Invalid request payload"})


@app.get("/")
def root():
    return {"status": "Orbata Core Running"}

