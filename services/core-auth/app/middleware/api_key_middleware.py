from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from datetime import datetime, timezone

from app.core.database import SessionLocal
from app.services.api_key_service import get_client_by_api_key


class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/otp"):
            api_key = request.headers.get("x-api-key")
            if not api_key:
                return JSONResponse(status_code=401, content={"detail": "Invalid API key"})

            db = SessionLocal()
            try:
                client = get_client_by_api_key(db, api_key)
            finally:
                db.close()

            if not client:
                return JSONResponse(status_code=401, content={"detail": "Invalid API key"})
            if client.expires_at and client.expires_at < datetime.now(timezone.utc):
                return JSONResponse(status_code=401, content={"detail": "API key expired"})

            display_name = client.email_from_name or client.name
            request.state.client = {
                "id": str(client.id),
                "name": client.name,
                "email_from_name": display_name,
            }

        return await call_next(request)
