"""Persist decrypted Matrix room messages in PostgreSQL (survives Railway redeploys)."""

from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models import CachedRoomMessage
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


def _parse_day(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def upsert_messages(messages: list[dict], *, room_id: str) -> None:
    """Save member/bot message payloads keyed by Matrix event id."""
    rows: list[dict] = []
    for msg in messages:
        event_id = str(msg.get("event_id") or msg.get("id") or "").strip()
        if not event_id:
            continue
        day = _parse_day(msg.get("day"))
        if day is None:
            sent = msg.get("sent_at")
            if sent:
                try:
                    from datetime import datetime

                    day = datetime.fromisoformat(str(sent)).date()
                except ValueError:
                    day = date.today()
            else:
                day = date.today()
        rows.append(
            {
                "room_id": room_id,
                "event_id": event_id,
                "day": day,
                "is_bot": bool(msg.get("is_bot")),
                "payload_json": dict(msg),
            }
        )
    if not rows:
        return

    db = SessionLocal()
    try:
        stmt = pg_insert(CachedRoomMessage).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["room_id", "event_id"],
            set_={
                "day": stmt.excluded.day,
                "is_bot": stmt.excluded.is_bot,
                "payload_json": stmt.excluded.payload_json,
            },
        )
        db.execute(stmt)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Failed to upsert room message cache for %s", room_id)
    finally:
        db.close()


def load_for_day(room_id: str, *, day: str, include_bot: bool = True) -> list[dict]:
    day_date = _parse_day(day)
    if day_date is None:
        return []
    db = SessionLocal()
    try:
        stmt = select(CachedRoomMessage).where(
            CachedRoomMessage.room_id == room_id,
            CachedRoomMessage.day == day_date,
        )
        if not include_bot:
            stmt = stmt.where(CachedRoomMessage.is_bot.is_(False))
        return [dict(row.payload_json) for row in db.scalars(stmt).all()]
    finally:
        db.close()


def load_for_range(
    room_id: str,
    *,
    since: date,
    until: date,
    include_bot: bool = True,
) -> list[dict]:
    db = SessionLocal()
    try:
        stmt = select(CachedRoomMessage).where(
            CachedRoomMessage.room_id == room_id,
            CachedRoomMessage.day >= since,
            CachedRoomMessage.day <= until,
        )
        if not include_bot:
            stmt = stmt.where(CachedRoomMessage.is_bot.is_(False))
        rows = db.scalars(stmt).all()
        out = [dict(row.payload_json) for row in rows]
        out.sort(key=lambda m: m.get("sent_at") or "")
        return out
    finally:
        db.close()


def import_json_file(path: Path) -> int:
    """One-shot: load member_feed_cache.json into Postgres. Returns message count."""
    if not path.is_file():
        return 0
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read room cache file %s", path)
        return 0
    if not isinstance(raw, dict):
        return 0

    count = 0
    for room_id, events in raw.items():
        if not isinstance(events, dict):
            continue
        msgs = [v for v in events.values() if isinstance(v, dict)]
        upsert_messages(msgs, room_id=room_id)
        count += len(msgs)
    logger.info("Imported %d cached room message(s) from %s", count, path)
    return count


def seed_from_file_if_empty(cache_file: Path) -> None:
    """Bootstrap: copy file cache into DB when the table is empty."""
    db = SessionLocal()
    try:
        if db.scalar(select(CachedRoomMessage.id).limit(1)) is not None:
            return
    finally:
        db.close()
    import_json_file(cache_file)
