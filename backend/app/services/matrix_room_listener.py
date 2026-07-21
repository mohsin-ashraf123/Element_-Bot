"""Persistent Matrix sync — decrypt member messages as they arrive."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import datetime, time as dt_time

from nio import MatrixRoom
from nio.events.room_events import RoomMessageText

from app.core.config import settings
from app.domain.calendar import tz
from app.services.matrix_client import get_session
from app.services.matrix_e2ee import (
    _auto_handle_verifications,
    _bootstrap_e2ee,
    _build_client,
    _flush_outgoing,
    _is_store_warm,
    _warm_lock,
    recover_megolm_events,
)
from nio.events.room_events import MegolmEvent
from app.services.matrix_room_feed import (
    _message_from_text_event,
    _persist_member_messages,
    invalidate_cache,
    merge_member_cache,
)

logger = logging.getLogger(__name__)

_listener_thread: threading.Thread | None = None
_listener_running = False
_stop = threading.Event()
_names_cache: dict[str, str] = {"@mohsinashraf:matrix.org": "Mohsin"}
_names_loaded_at = 0.0


def _sync_filter_for_rooms(room_ids: list[str]) -> dict:
    return {
        "room": {
            "rooms": room_ids,
            "timeline": {"limit": 25},
            "state": {"lazy_load_members": False},
            "ephemeral": {"lazy_load_members": True},
        }
    }


def _refresh_mxid_names() -> dict[str, str]:
    global _names_cache, _names_loaded_at
    now = time.monotonic()
    if now - _names_loaded_at < 300:
        return _names_cache
    try:
        from app.db.session import SessionLocal
        from app.services import team_service

        db = SessionLocal()
        try:
            _names_cache = {
                m.matrix_user_id: m.name
                for m in team_service.list_members(db)
                if m.matrix_user_id
            }
            _names_cache.setdefault("@mohsinashraf:matrix.org", "Mohsin")
            _names_loaded_at = now
        finally:
            db.close()
    except Exception as exc:
        logger.debug("Listener name cache refresh skipped: %s", exc)
    return _names_cache


def _zone_name() -> str:
    try:
        from app.db.session import SessionLocal
        from app.services import settings_service

        db = SessionLocal()
        try:
            sched = settings_service.get_setting(db, "schedule")
            return sched.get("timezone", settings.timezone)
        finally:
            db.close()
    except Exception:
        return settings.timezone


async def _backfill_today(
    client,
    room_id: str,
    *,
    zone_name: str,
) -> None:
    """One-shot key recovery for today's undecrypted member messages."""
    from nio.events.room_events import RoomMessageText

    zone = tz(zone_name)
    today = datetime.now(zone).date()
    day_start = datetime.combine(today, dt_time.min, tzinfo=zone)
    day_end = datetime.combine(today, dt_time.max, tzinfo=zone)
    bot_user = settings.matrix_bot_username
    names = _refresh_mxid_names()
    pending: list[MegolmEvent] = []
    seen: set[str] = set()

    resp = await client.room_messages(room_id, limit=40, direction="b")
    for event in resp.chunk or []:
        if isinstance(event, RoomMessageText):
            row = _message_from_text_event(
                event,
                zone=zone,
                day_start=day_start,
                day_end=day_end,
                bot_user=bot_user,
                mxid_to_name=names,
                seen=seen,
            )
            if row and not row.get("is_bot"):
                _persist_member_messages(room_id, [row], day=today.isoformat())
            continue
        if isinstance(event, MegolmEvent):
            origin_ms = int(getattr(event, "server_timestamp", 0) or 0)
            if not origin_ms and hasattr(event, "source"):
                origin_ms = int(event.source.get("origin_server_ts", 0) or 0)
            if not origin_ms:
                continue
            sent_at = datetime.fromtimestamp(origin_ms / 1000, tz=zone)
            if day_start <= sent_at <= day_end:
                pending.append(event)

    if not pending:
        return

    recovered = await recover_megolm_events(client, room_id, pending, max_rounds=3)
    for event in recovered:
        if isinstance(event, RoomMessageText):
            row = _message_from_text_event(
                event,
                zone=zone,
                day_start=day_start,
                day_end=day_end,
                bot_user=bot_user,
                mxid_to_name=names,
                seen=seen,
            )
            if row and not row.get("is_bot"):
                _persist_member_messages(room_id, [row], day=today.isoformat())
                invalidate_cache(room_id)
                logger.info("Backfilled member message from %s", row.get("label"))


def _target_rooms() -> list[str]:
    rooms = [settings.matrix_room_id.strip()]
    task = settings.matrix_task_room_id.strip()
    if task:
        rooms.append(task)
    return [r for r in rooms if r]


async def _listen_async() -> None:
    sess = get_session()
    room_ids = _target_rooms()
    if not room_ids:
        return

    zone_name = _zone_name()
    zone = tz(zone_name)
    bot_user = settings.matrix_bot_username
    client, store_path = _build_client(sess.access_token, sess.device_id)
    seen: set[str] = set()

    async def _on_room_message(room: MatrixRoom, event: RoomMessageText) -> None:
        if room.room_id not in room_ids:
            return
        today = datetime.now(zone).date()
        day_start = datetime.combine(today, dt_time.min, tzinfo=zone)
        day_end = datetime.combine(today, dt_time.max, tzinfo=zone)
        names = _refresh_mxid_names()
        row = _message_from_text_event(
            event,
            zone=zone,
            day_start=day_start,
            day_end=day_end,
            bot_user=bot_user,
            mxid_to_name=names,
            seen=seen,
        )
        if not row or row.get("is_bot"):
            return
        _persist_member_messages(room.room_id, [row], day=today.isoformat())
        invalidate_cache(room.room_id)
        logger.info(
            "Listener captured member message in %s from %s",
            room.room_id,
            row.get("label"),
        )
        from app.services import analysis_service

        analysis_service.invalidate_cache()

    client.add_event_callback(_on_room_message, RoomMessageText)
    room_filter = _sync_filter_for_rooms(room_ids)

    try:
        with _warm_lock:
            for room_id in room_ids:
                await _bootstrap_e2ee(
                    client,
                    room_id,
                    warm=_is_store_warm(store_path),
                    skip_keys=False,
                )
            await _backfill_today(client, room_ids[0], zone_name=zone_name)

        logger.info("Matrix room listener started for %s", room_ids)
        while not _stop.is_set():
            await client.sync(timeout=30_000, sync_filter=room_filter)
            await _auto_handle_verifications(client)
            await _flush_outgoing(client)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Matrix room listener stopped with error")
    finally:
        await client.close()


def listener_active() -> bool:
    return _listener_running


def _listener_runner() -> None:
    global _listener_running
    from app.services.matrix_room_feed import _start_matrix_loop, _run_matrix_async

    time.sleep(25)
    while not _stop.is_set():
        try:
            _listener_running = True
            _run_matrix_async(_listen_async(), timeout=None)
        except Exception:
            logger.exception("Matrix listener loop crashed — retrying in 15s")
            time.sleep(15)
        finally:
            _listener_running = False


def start_listener() -> None:
    """Background sync so E2EE member messages decrypt while the bot is online."""
    global _listener_thread
    if _listener_thread and _listener_thread.is_alive():
        return
    if not settings.matrix_room_id.strip():
        return
    _stop.clear()
    _listener_thread = threading.Thread(
        target=_listener_runner,
        daemon=True,
        name="matrix-room-listener",
    )
    _listener_thread.start()


def stop_listener() -> None:
    _stop.set()
