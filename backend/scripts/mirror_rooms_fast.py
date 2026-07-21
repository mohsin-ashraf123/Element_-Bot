"""Fast Element room mirror — sync + paginate + decrypt, no cold key rounds.

Run:  .\\venv\\Scripts\\python.exe scripts\\mirror_rooms_fast.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("mirror")


async def mirror_room(client, room_id: str, *, zone_name: str, days: int = 10) -> list[dict]:
    from nio.events.room_events import MegolmEvent, RoomMessageText
    from nio.responses import RoomMessagesError

    from app.core.config import settings
    from app.domain.calendar import tz
    from app.services.matrix_e2ee import recover_megolm_events
    from app.services.matrix_room_feed import (
        _message_from_text_event,
        _persist_member_messages,
        invalidate_cache,
    )
    from app.db.session import SessionLocal
    from app.services import team_service

    zone = tz(zone_name)
    today = datetime.now(zone).date()
    day_start = datetime.combine(today - timedelta(days=days), dt_time.min, tzinfo=zone)
    day_end = datetime.combine(today, dt_time.max, tzinfo=zone)
    bot_user = settings.matrix_bot_username

    db = SessionLocal()
    try:
        mxid_to_name = {
            m.matrix_user_id: m.name
            for m in team_service.list_members(db)
            if m.matrix_user_id
        }
        mxid_to_name.setdefault("@mohsinashraf:matrix.org", "Mohsin")
    finally:
        db.close()

    # Load room into client.rooms via sync (no member-key storm).
    await client.sync(
        timeout=20_000,
        full_state=True,
        sync_filter={
            "room": {
                "rooms": [room_id],
                "timeline": {"limit": 50},
                "state": {"lazy_load_members": False},
            }
        },
    )
    if room_id not in client.rooms:
        await client.sync(timeout=20_000, full_state=True)
    if room_id not in client.rooms:
        raise RuntimeError(f"Room {room_id} not in client after sync")

    out: list[dict] = []
    seen: set[str] = set()
    pending: list[MegolmEvent] = []
    page_from: str | None = None

    for page in range(25):
        resp = await client.room_messages(room_id, start=page_from, limit=100, direction="b")
        if isinstance(resp, RoomMessagesError) or not getattr(resp, "chunk", None):
            log.warning("page %s failed: %s", page, getattr(resp, "message", resp))
            break
        reached_old = False
        for event in resp.chunk:
            if isinstance(event, RoomMessageText):
                row = _message_from_text_event(
                    event,
                    zone=zone,
                    day_start=day_start,
                    day_end=day_end,
                    bot_user=bot_user,
                    mxid_to_name=mxid_to_name,
                    seen=seen,
                )
                if row:
                    out.append(row)
                continue
            if isinstance(event, MegolmEvent):
                origin_ms = int(getattr(event, "server_timestamp", 0) or 0)
                if not origin_ms and hasattr(event, "source"):
                    origin_ms = int(event.source.get("origin_server_ts", 0) or 0)
                if not origin_ms:
                    continue
                sent_at = datetime.fromtimestamp(origin_ms / 1000, tz=zone)
                if sent_at < day_start:
                    reached_old = True
                    continue
                if sent_at <= day_end:
                    pending.append(event)
        page_from = resp.end
        log.info(
            "page %s: decrypted=%s pending_megolm=%s",
            page,
            len(out),
            len(pending),
        )
        if reached_old or not page_from:
            break

    if pending:
        log.info("Recovering %s megolm events…", len(pending))
        recovered = await recover_megolm_events(client, room_id, pending, max_rounds=6)
        for event in recovered:
            if isinstance(event, RoomMessageText):
                row = _message_from_text_event(
                    event,
                    zone=zone,
                    day_start=day_start,
                    day_end=day_end,
                    bot_user=bot_user,
                    mxid_to_name=mxid_to_name,
                    seen=seen,
                )
                if row:
                    out.append(row)
                    log.info("Recovered: %s | %s", row.get("label"), (row.get("text") or "")[:50])

    out.sort(key=lambda m: m.get("sent_at") or "")
    _persist_member_messages(room_id, out, zone_name=zone_name, fallback_day=today.isoformat())
    invalidate_cache(room_id)
    return out


async def main() -> None:
    from app.core.config import settings
    from app.services.matrix_client import get_session, invalidate_session
    from app.services.matrix_e2ee import _build_client, _warm_lock
    from app.services.matrix_room_listener import _zone_name

    invalidate_session()
    sess = get_session()
    zone = _zone_name()
    rooms = [r for r in (settings.matrix_room_id.strip(), settings.matrix_task_room_id.strip()) if r]
    client, _ = _build_client(sess.access_token, sess.device_id)
    try:
        with _warm_lock:
            for room_id in rooms:
                log.info("=== Mirroring %s ===", room_id)
                rows = await mirror_room(client, room_id, zone_name=zone, days=10)
                print(f"\n{room_id[:22]}… → {len(rows)} messages")
                for m in rows:
                    print(
                        f"  {(m.get('sent_at') or '')[5:16]} | {m.get('label'):12} | "
                        f"{(m.get('text') or '').splitlines()[0][:65]}"
                    )
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
