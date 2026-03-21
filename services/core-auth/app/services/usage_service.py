import uuid

from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.usage import Usage, utc_today

CHANNEL_EMAIL = "email"


def _parse_client_id(client_id: str) -> uuid.UUID:
    return uuid.UUID(str(client_id))


def increment_sent(db: Session, client_id: str, channel: str = CHANNEL_EMAIL) -> None:
    """Upsert: +1 sent_count for (client, UTC date, channel)."""
    cid = _parse_client_id(client_id)
    today = utc_today()
    stmt = (
        pg_insert(Usage)
        .values(
            id=uuid.uuid4(),
            client_id=cid,
            date=today,
            channel=channel,
            sent_count=1,
            success_count=0,
            fail_count=0,
        )
        .on_conflict_do_update(
            constraint="uq_usage_client_date_channel",
            set_={"sent_count": Usage.sent_count + 1},
        )
    )
    db.execute(stmt)
    db.commit()


def list_usage_for_client(
    db: Session, client_id: str, limit: int = 366
) -> list[dict]:
    """Recent usage rows for admin API (newest dates first)."""
    cid = _parse_client_id(client_id)
    stmt = (
        select(Usage)
        .where(Usage.client_id == cid)
        .order_by(desc(Usage.date), desc(Usage.channel))
        .limit(limit)
    )
    rows = db.execute(stmt).scalars().all()
    return [
        {
            "date": row.date.isoformat(),
            "sent_count": row.sent_count,
            "success_count": row.success_count,
            "fail_count": row.fail_count,
        }
        for row in rows
    ]
