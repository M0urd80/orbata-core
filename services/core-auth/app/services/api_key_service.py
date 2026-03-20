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


def create_client_with_api_key(db: Session, name: str) -> tuple[Client, str]:
    raw_api_key = generate_api_key()
    client = Client(name=name, api_key=hash_api_key(raw_api_key))
    db.add(client)
    db.commit()
    db.refresh(client)
    return client, raw_api_key


def create_client(db: Session, name: str) -> str:
    _, raw_api_key = create_client_with_api_key(db, name)
    return raw_api_key


def create_client_with_expiration(
    db: Session, name: str, expires_in_days: int | None = None
) -> tuple[Client, str]:
    raw_api_key = generate_api_key()
    expires_at = None
    if expires_in_days is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

    client = Client(name=name, api_key=hash_api_key(raw_api_key), expires_at=expires_at)
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
