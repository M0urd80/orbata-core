import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.client import Client
from app.services.plan_defaults import resolve_plan_id_for_new_client

if TYPE_CHECKING:
    from starlette.requests import Request


def generate_api_key(length: int = 32) -> str:
    """Raw client secret: ``orb_live_`` + ``secrets.token_urlsafe(length)`` (stored hashed)."""
    return f"orb_live_{secrets.token_urlsafe(length)}"


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def get_client_by_api_key(db: Session, api_key: str) -> Client | None:
    """Lookup by hashed key (may be inactive — caller must check ``is_active`` / expiry)."""
    stmt = select(Client).where(Client.api_key == hash_api_key(api_key))
    return db.execute(stmt).scalars().first()


class ClientAuthError(Exception):
    """Invalid or unusable ``x-api-key`` (maps to HTTP 401)."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


def require_client_from_api_key_header(db: Session, request: "Request") -> Client:
    """
    Step 1–2 of OTP auth: read ``x-api-key``, resolve row via ``api_key`` hash.
    Use ``client.id`` from this object for usage, quotas, and logging (same ``db`` session).
    """
    api_key = request.headers.get("x-api-key")
    if not api_key:
        raise ClientAuthError(401, "Invalid API key")
    client = get_client_by_api_key(db, api_key)
    if not client:
        raise ClientAuthError(401, "Invalid API key")
    if not client.is_active:
        raise ClientAuthError(401, "API key revoked or inactive")
    if client.expires_at and client.expires_at < datetime.now(timezone.utc):
        raise ClientAuthError(401, "API key expired")
    return client


def create_client_with_api_key(
    db: Session,
    name: str,
    email_from_name: str | None,
    *,
    plan_id: UUID | None,
) -> tuple[Client, str]:
    resolved_plan_id = resolve_plan_id_for_new_client(db, plan_id)
    raw_api_key = generate_api_key()
    branding = (email_from_name.strip() if email_from_name else None) or name
    client = Client(
        name=name,
        api_key=hash_api_key(raw_api_key),
        email_from_name=branding,
        plan_id=resolved_plan_id,
        created_at=datetime.utcnow(),
        is_active=True,
    )
    db.add(client)
    try:
        db.flush()
        db.commit()
        db.refresh(client)
    except Exception:
        db.rollback()
        raise
    return client, raw_api_key


def create_client(
    db: Session,
    name: str,
    email_from_name: str | None,
    *,
    plan_id: UUID | None,
) -> tuple:
    client, raw_api_key = create_client_with_api_key(
        db, name, email_from_name, plan_id=plan_id
    )
    return client.id, raw_api_key


def create_client_with_expiration(
    db: Session,
    name: str,
    *,
    plan_id: UUID | None,
    expires_in_days: int | None = None,
) -> tuple[Client, str]:
    resolved_plan_id = resolve_plan_id_for_new_client(db, plan_id)
    raw_api_key = generate_api_key()
    expires_at = None
    if expires_in_days is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

    client = Client(
        name=name,
        api_key=hash_api_key(raw_api_key),
        expires_at=expires_at,
        email_from_name=name,
        plan_id=resolved_plan_id,
        created_at=datetime.utcnow(),
        is_active=True,
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    return client, raw_api_key


def rotate_api_key(
    db: Session, client_id: UUID, expires_in_days: int | None = None
) -> tuple[Client, str] | None:
    client = db.get(Client, client_id)
    if not client:
        return None

    raw_api_key = generate_api_key()
    client.api_key = hash_api_key(raw_api_key)
    client.rotated_at = datetime.now(timezone.utc)
    client.is_active = True
    if expires_in_days is not None:
        client.expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

    db.commit()
    db.refresh(client)
    return client, raw_api_key


def revoke_api_key(db: Session, client_id: UUID) -> Client | None:
    client = db.get(Client, client_id)
    if not client:
        return None
    client.is_active = False
    db.add(client)
    db.commit()
    db.refresh(client)
    return client
