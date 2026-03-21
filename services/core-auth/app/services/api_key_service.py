import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.client import Client


def generate_api_key(length: int = 48) -> str:
    return f"orb_live_{secrets.token_urlsafe(length)}"


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()


def get_client_by_api_key(db: Session, api_key: str) -> Client | None:
    stmt = select(Client).where(Client.api_key == hash_api_key(api_key))
    return db.execute(stmt).scalar_one_or_none()


def create_client_with_api_key(
    db: Session, name: str, email_from_name: str | None = None
) -> tuple[Client, str]:
    raw_api_key = generate_api_key()
    branding = (email_from_name.strip() if email_from_name else None) or name
    client = Client(
        name=name,
        api_key=hash_api_key(raw_api_key),
        email_from_name=branding,
        created_at=datetime.utcnow(),
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
    db: Session, name: str, email_from_name: str | None = None
) -> tuple:
    client, raw_api_key = create_client_with_api_key(db, name, email_from_name)
    return client.id, raw_api_key


def create_client_with_expiration(
    db: Session, name: str, expires_in_days: int | None = None
) -> tuple[Client, str]:
    raw_api_key = generate_api_key()
    expires_at = None
    if expires_in_days is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

    client = Client(
        name=name,
        api_key=hash_api_key(raw_api_key),
        expires_at=expires_at,
        email_from_name=name,
        created_at=datetime.utcnow(),
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
    if expires_in_days is not None:
        client.expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

    db.commit()
    db.refresh(client)
    return client, raw_api_key
