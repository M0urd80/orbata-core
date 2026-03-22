from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.database import SessionLocal
from app.services.api_key_service import (
    ClientAuthError,
    require_client_from_api_key_header,
)


class ApiKeyMiddleware(BaseHTTPMiddleware):
    """
    Early reject bad ``/otp`` requests. The handler re-resolves the client on ``get_db()``
    so usage / quotas / logs use the same session-bound row as ``client.id``.
    """

    async def dispatch(self, request: Request, call_next):
        if request.url.path.startswith("/otp"):
            db = SessionLocal()
            try:
                require_client_from_api_key_header(db, request)
            except ClientAuthError as e:
                return JSONResponse(
                    status_code=e.status_code, content={"detail": e.detail}
                )
            finally:
                db.close()

        return await call_next(request)
