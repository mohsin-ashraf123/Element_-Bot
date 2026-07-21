"""One-shot: mirror Element rooms into Postgres (decrypt + persist).

Run:  .\\venv\\Scripts\\python.exe scripts\\backfill_rooms.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("backfill")


async def main() -> None:
    from app.core.config import settings
    from app.services.matrix_client import get_session, invalidate_session
    from app.services.matrix_e2ee import (
        _bootstrap_e2ee,
        _build_client,
        _is_store_warm,
        _warm_lock,
    )
    from app.services.matrix_room_listener import _backfill_range, _zone_name

    invalidate_session()
    sess = get_session(force_login=True)
    zone = _zone_name()
    rooms = [r for r in (settings.matrix_room_id, settings.matrix_task_room_id) if r.strip()]
    client, store_path = _build_client(sess.access_token, sess.device_id)
    try:
        with _warm_lock:
            for room_id in rooms:
                logger.info("Bootstrapping E2EE for %s …", room_id)
                await _bootstrap_e2ee(
                    client,
                    room_id,
                    warm=_is_store_warm(store_path),
                    skip_keys=False,
                )
            for room_id in rooms:
                logger.info("Backfilling %s …", room_id)
                await _backfill_range(client, room_id, zone_name=zone, days=14, max_pages=20)
        logger.info("Backfill complete")
    finally:
        await client.close()

    from app.services.matrix_room_feed import recent_room_timeline

    for room_id in rooms:
        rows = recent_room_timeline(room_id, zone_name=zone, limit=30)
        print(f"\n=== {room_id[:18]}… ({len(rows)} msgs) ===")
        for m in rows:
            text = (m.get("text") or "").replace("\n", " | ")[:70]
            print(f"  {(m.get('sent_at') or '')[5:16]} | {m.get('label')} | {text}")


if __name__ == "__main__":
    asyncio.run(main())
