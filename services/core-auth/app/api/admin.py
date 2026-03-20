from uuid import UUID

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.core.config import ADMIN_SECRET
from app.core.database import SessionLocal
from app.services.api_key_service import create_client_with_expiration, rotate_api_key

router = APIRouter()


class CreateClientRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    expires_in_days: int | None = Field(default=None, ge=1)


class RotateApiKeyRequest(BaseModel):
    expires_in_days: int | None = Field(default=None, ge=1)


def require_admin_secret(secret: str | None):
    if not secret or secret != ADMIN_SECRET:
        raise HTTPException(status_code=401, detail="Invalid admin secret")


@router.post("/clients")
def create_client(data: CreateClientRequest, x_admin_secret: str | None = Header(default=None)):
    require_admin_secret(x_admin_secret)
    db = SessionLocal()
    try:
        client, raw_api_key = create_client_with_expiration(
            db, data.name, data.expires_in_days
        )
    finally:
        db.close()

    return {
        "id": str(client.id),
        "name": client.name,
        "api_key": raw_api_key,
        "expires_at": client.expires_at.isoformat() if client.expires_at else None,
    }


@router.post("/clients/{client_id}/rotate")
def rotate_client_key(
    client_id: UUID,
    data: RotateApiKeyRequest,
    x_admin_secret: str | None = Header(default=None),
):
    require_admin_secret(x_admin_secret)
    db = SessionLocal()
    try:
        rotated = rotate_api_key(db, client_id, data.expires_in_days)
    finally:
        db.close()

    if not rotated:
        raise HTTPException(status_code=404, detail="Client not found")

    client, raw_api_key = rotated
    return {
        "id": str(client.id),
        "name": client.name,
        "api_key": raw_api_key,
        "expires_at": client.expires_at.isoformat() if client.expires_at else None,
        "rotated_at": client.rotated_at.isoformat() if client.rotated_at else None,
    }
