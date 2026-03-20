from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import ADMIN_SECRET
from app.core.database import get_db
from app.schemas.client import ClientCreateRequest, ClientCreateResponse
from app.services.api_key_service import create_client, rotate_api_key
from app.services.usage_service import get_usage_today

router = APIRouter()


class RotateApiKeyRequest(BaseModel):
    expires_in_days: int | None = Field(default=None, ge=1)


def require_admin_secret(secret: str | None):
    if not secret or secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Invalid admin secret")


@router.get("/usage/{client_id}")
def get_usage(
    client_id: str,
    x_admin_secret: str | None = Header(default=None),
):
    require_admin_secret(x_admin_secret)
    return get_usage_today(client_id)


@router.post("/clients", response_model=ClientCreateResponse)
def create_client_endpoint(
    data: ClientCreateRequest,
    x_admin_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    require_admin_secret(x_admin_secret)
    client_id, api_key = create_client(db, data.name)
    return {"client_id": str(client_id), "api_key": api_key}


@router.post("/clients/{client_id}/rotate")
def rotate_client_key(
    client_id: UUID,
    data: RotateApiKeyRequest,
    x_admin_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    require_admin_secret(x_admin_secret)
    rotated = rotate_api_key(db, client_id, data.expires_in_days)
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
