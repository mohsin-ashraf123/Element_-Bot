"""WebSocket hub — push room feed updates to connected dashboards."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)

_SYNC_SECONDS = 15
_hub: FeedHub | None = None


class FeedHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._last_sig: str | None = None
        self._stop = threading.Event()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        with self._lock:
            self._clients.add(ws)
        logger.info("Feed WS client connected (%d total)", len(self._clients))

    def disconnect(self, ws: WebSocket) -> None:
        with self._lock:
            self._clients.discard(ws)

    @staticmethod
    def _signature(payload: dict[str, Any]) -> str:
        msgs = payload.get("today_messages") or []
        return json.dumps(
            [(m.get("id"), m.get("sent_at"), m.get("text", "")[:40]) for m in msgs],
            sort_keys=True,
        )

    async def broadcast(self, payload: dict[str, Any], *, force: bool = False) -> None:
        sig = self._signature(payload)
        if not force and sig == self._last_sig:
            return
        self._last_sig = sig

        with self._lock:
            clients = list(self._clients)
        if not clients:
            return

        message = {"type": "feed", "data": payload}
        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)
        if clients:
            logger.debug("Feed WS broadcast to %d client(s)", len(clients) - len(dead))

    def push_from_thread(self, payload: dict[str, Any], *, force: bool = False) -> None:
        loop = self._loop
        if loop is None or not loop.is_running():
            return
        asyncio.run_coroutine_threadsafe(self.broadcast(payload, force=force), loop)

    def _build_and_push(self) -> None:
        from app.core.config import settings
        from app.db.session import SessionLocal
        from app.services import dashboard_service, matrix_room_feed, settings_service, team_service

        db = SessionLocal()
        try:
            schedule = settings_service.get_setting(db, "schedule")
            zone_name = schedule.get("timezone", settings.timezone)
            mxid_to_name = {
                m.matrix_user_id: m.name
                for m in team_service.list_members(db)
                if m.matrix_user_id
            }
            mxid_to_name.setdefault("@mohsinashraf:matrix.org", "Mohsin")
            pairing_id = settings.matrix_room_id
            age = matrix_room_feed.cache_age(pairing_id)
            if age is None or age >= 10:
                try:
                    matrix_room_feed.fetch_today_messages(
                        room_id=pairing_id,
                        zone_name=zone_name,
                        mxid_to_name=mxid_to_name,
                        stale_ok=False,
                        block=True,
                    )
                except Exception:
                    logger.debug("Feed hub matrix fetch skipped", exc_info=True)
            payload = dashboard_service.build_feed(db)
            self.push_from_thread(payload)
        except Exception:
            logger.exception("Feed hub sync failed")
        finally:
            db.close()

    def _sync_loop(self) -> None:
        time.sleep(5)
        while not self._stop.is_set():
            try:
                self._build_and_push()
            except Exception:
                logger.exception("Feed hub loop error")
            self._stop.wait(_SYNC_SECONDS)

    def start_background_sync(self) -> None:
        threading.Thread(target=self._sync_loop, daemon=True, name="feed-hub-sync").start()

    def stop(self) -> None:
        self._stop.set()


def get_hub() -> FeedHub:
    global _hub
    if _hub is None:
        _hub = FeedHub()
    return _hub


def notify_feed_update(payload: dict[str, Any], *, force: bool = False) -> None:
    get_hub().push_from_thread(payload, force=force)
