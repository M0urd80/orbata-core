from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import ADMIN_SECRET
from app.core.database import get_db
from app.models.client import Client
from app.models.email_log import EmailLog
from app.models.plan import Plan
from app.schemas.client import ClientCreateResponse, CreateClientRequest
from app.schemas.plan import PlanCreateRequest, PlanOut
from app.services.api_key_service import (
    create_client,
    revoke_api_key,
    rotate_api_key,
)
from app.services.usage_service import list_usage_for_client

router = APIRouter()


class RotateApiKeyRequest(BaseModel):
    expires_in_days: int | None = Field(default=None, ge=1)


def require_admin_secret(secret: str | None):
    if not secret or secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Invalid admin secret")


def require_admin_secret_request(request: Request) -> None:
    """Validate ``x-admin-secret`` header (same value as ``ADMIN_SECRET`` env, not hardcoded)."""
    secret = request.headers.get("x-admin-secret")
    if not secret or secret != ADMIN_SECRET:
        raise HTTPException(status_code=403, detail="Invalid admin secret")


@router.get("/usage/{client_id}")
def get_usage(
    client_id: str,
    x_admin_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    require_admin_secret(x_admin_secret)
    return list_usage_for_client(db, client_id)


@router.get("/logs/{client_id}")
def get_email_logs(
    client_id: UUID,
    x_admin_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    require_admin_secret(x_admin_secret)
    stmt = (
        select(EmailLog)
        .where(EmailLog.client_id == client_id)
        .order_by(desc(EmailLog.created_at))
        .limit(50)
    )
    rows = db.execute(stmt).scalars().all()
    return [
        {
            "id": str(row.id),
            "client_id": str(row.client_id),
            "email": row.email,
            "status": row.status,
            "attempts": row.attempts,
            "error_message": row.error_message,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


@router.get("/plans")
def list_plans(
    x_admin_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    require_admin_secret(x_admin_secret)
    rows = db.execute(select(Plan).order_by(Plan.name)).scalars().all()
    return [PlanOut.from_orm_row(p).model_dump() for p in rows]


@router.post("/plans")
def create_plan(
    data: PlanCreateRequest,
    x_admin_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    require_admin_secret(x_admin_secret)
    name = data.name.strip()
    dup = db.execute(select(Plan).where(Plan.name == name)).scalars().first()
    if dup:
        raise HTTPException(status_code=409, detail="Plan name already exists")
    plan = Plan(name=name, price=data.price)
    db.add(plan)
    try:
        db.commit()
        db.refresh(plan)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500, detail=f"Could not create plan: {e!s}"
        ) from e
    return PlanOut.from_orm_row(plan).model_dump()


@router.delete("/plans/{plan_id}")
def delete_plan(
    plan_id: UUID,
    x_admin_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    require_admin_secret(x_admin_secret)
    plan = db.get(Plan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    db.delete(plan)
    db.commit()
    return {"ok": True}


@router.post("/clients", response_model=ClientCreateResponse)
def create_client_endpoint(
    request: Request,
    payload: CreateClientRequest,
    db: Session = Depends(get_db),
):
    require_admin_secret_request(request)
    # JSON body — not query parameters.
    data = (
        payload.model_dump()
        if hasattr(payload, "model_dump")
        else payload.dict()
    )
    plan_uuid: UUID | None = None
    raw_plan = data.get("plan_id")
    if raw_plan is not None and str(raw_plan).strip():
        try:
            plan_uuid = UUID(str(raw_plan).strip())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid plan_id")
    try:
        # API key: orb_live_ + secrets.token_urlsafe(...) inside create_client → generate_api_key
        client_id, api_key = create_client(
            db,
            data["name"],
            data.get("email_from_name"),
            plan_id=plan_uuid,
        )
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Could not create client: {e!s}",
        ) from e
    persisted = db.get(Client, client_id)
    if persisted is None:
        raise HTTPException(
            status_code=500,
            detail="Client was not persisted to the database",
        )
    return {"client_id": str(client_id), "api_key": api_key}


def _rotate_client_key_impl(
    client_id: UUID,
    data: RotateApiKeyRequest,
    db: Session,
):
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


@router.post("/clients/{client_id}/rotate")
def rotate_client_key(
    client_id: UUID,
    data: RotateApiKeyRequest,
    x_admin_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    require_admin_secret(x_admin_secret)
    return _rotate_client_key_impl(client_id, data, db)


@router.post("/clients/{client_id}/rotate-key")
def rotate_client_key_alias(
    client_id: UUID,
    data: RotateApiKeyRequest,
    x_admin_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    """Alias for ``POST /clients/{id}/rotate`` (returns new raw ``api_key`` once)."""
    require_admin_secret(x_admin_secret)
    return _rotate_client_key_impl(client_id, data, db)


@router.post("/clients/{client_id}/revoke")
def revoke_client_key(
    client_id: UUID,
    x_admin_secret: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    require_admin_secret(x_admin_secret)
    client = revoke_api_key(db, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    return {"status": "revoked", "id": str(client.id), "is_active": client.is_active}
