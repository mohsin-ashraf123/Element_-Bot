"""Fetch decrypted room timelines for the dashboard feed."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from datetime import date, datetime, time as dt_time

from pathlib import Path

from nio.events import Event
from nio.events.room_events import MegolmEvent, RoomMessageText

from app.core.config import settings
from app.domain.calendar import tz, month_bounds
from app.services.matrix_client import e2ee_passphrase, e2ee_store_for_device, get_session
from app.services.matrix_e2ee import (
    _build_client,
    _ensure_room_ready,
    _is_store_warm,
    _light_sync,
    _warm_lock,
    _warmed_devices,
)

logger = logging.getLogger(__name__)

_CACHE_TTL = 30.0
_STALE_MAX = 900.0
_MEMBER_CACHE_PATH = Path("./data/member_feed_cache.json")
_cache: dict[str, tuple[float, list[dict]]] = {}
_refreshing: set[str] = set()
_fetch_lock = threading.Lock()
_member_cache_lock = threading.Lock()
_loop: asyncio.AbstractEventLoop | None = None
_loop_thread: threading.Thread | None = None
_loop_ready = threading.Event()

def _start_matrix_loop() -> asyncio.AbstractEventLoop:
    """Single background event loop — avoids asyncio.run() crashes in thread pool."""
    global _loop, _loop_thread

    if _loop is not None and _loop.is_running():
        return _loop

    loop = asyncio.new_event_loop()

    def _runner() -> None:
        asyncio.set_event_loop(loop)
        _loop_ready.set()
        loop.run_forever()

    _loop_thread = threading.Thread(target=_runner, daemon=True, name="matrix-async-loop")
    _loop_thread.start()
    _loop_ready.wait(timeout=10)
    _loop = loop
    return loop


def _run_fetch_isolated(coro, *, timeout: float = 90.0):
    """Isolated event loop per fetch — avoids E2EE store clashes with the listener."""
    holder: list = []
    errors: list[BaseException] = []

    def _runner() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            holder.append(loop.run_until_complete(coro))
        except BaseException as exc:
            errors.append(exc)
        finally:
            loop.close()

    thread = threading.Thread(target=_runner, daemon=True, name="matrix-fetch-isolated")
    thread.start()
    thread.join(timeout=timeout + 10)
    if thread.is_alive():
        raise TimeoutError(f"Matrix fetch timed out after {timeout}s")
    if errors:
        raise errors[0]
    if not holder:
        return []
    return holder[0]


def _run_matrix_async(coro, *, timeout: float | None = 120.0):
    """Prefer isolated fetch loops; shared loop is only for the long-running listener."""
    try:
        from app.services.matrix_room_listener import listener_active

        if listener_active():
            return _run_fetch_isolated(coro, timeout=timeout or 90.0)
    except Exception:
        pass
    loop = _start_matrix_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    if timeout is None:
        return future.result()
    return future.result(timeout=timeout)


def invalidate_cache(room_id: str | None = None) -> None:
    if room_id:
        _cache.pop(room_id, None)
    else:
        _cache.clear()


def combine_feed_sources(primary: list[dict], secondary: list[dict]) -> list[dict]:
    """Merge Matrix live timeline with DB bot fallback — any room member, any sender."""
    by_key: dict[str, dict] = {}
    order: list[str] = []

    def _key(msg: dict) -> str:
        eid = msg.get("event_id") or msg.get("id")
        if eid:
            return str(eid)
        return f"{msg.get('sender')}:{msg.get('sent_at')}:{msg.get('text', '')[:40]}"

    for msg in secondary:
        k = _key(msg)
        by_key[k] = msg
        order.append(k)

    for msg in primary:
        k = _key(msg)
        if k not in by_key:
            order.append(k)
        by_key[k] = msg

    merged = [by_key[k] for k in order if k in by_key]
    merged.sort(key=lambda m: m.get("sent_at") or "")
    return _dedupe_bot_repeats(merged)


def feed_incomplete(messages: list[dict]) -> bool:
    if not messages:
        return True
    return not any(not m.get("is_bot") for m in messages)


def peek_cached(room_id: str) -> list[dict] | None:
    """Return cached messages without triggering a fetch."""
    if not room_id:
        return None
    cached = _cache.get(room_id)
    return list(cached[1]) if cached else None


def cache_age(room_id: str) -> float | None:
    cached = _cache.get(room_id)
    if not cached:
        return None
    return time.monotonic() - cached[0]


def dedupe_bot_messages(messages: list[dict]) -> list[dict]:
    """Public wrapper — collapse repeated bot posts in a timeline."""
    return _dedupe_bot_repeats(messages)


def _dedupe_bot_repeats(messages: list[dict]) -> list[dict]:
    seen_bot: set[tuple[str, str]] = set()
    seen_bot_text: set[str] = set()
    out: list[dict] = []
    for msg in messages:
        if msg.get("is_bot"):
            text = (msg.get("text") or "").strip()
            minute = (msg.get("sent_at") or "")[:16]
            key = (text, minute)
            if key in seen_bot:
                continue
            # Collapse repeated test sends with identical body on the same day.
            if text and text in seen_bot_text:
                continue
            seen_bot.add(key)
            if text:
                seen_bot_text.add(text)
        out.append(msg)
    return out


def _display_name(sender: str, mxid_to_name: dict[str, str]) -> str:
    if sender in mxid_to_name:
        return mxid_to_name[sender]
    if sender.startswith("@"):
        return sender[1:].split(":", 1)[0]
    return sender


def _load_member_cache_file() -> dict[str, dict[str, dict]]:
    _MEMBER_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not _MEMBER_CACHE_PATH.is_file():
        return {}
    try:
        raw = json.loads(_MEMBER_CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _save_member_cache_file(data: dict[str, dict[str, dict]]) -> None:
    _MEMBER_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _MEMBER_CACHE_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_MEMBER_CACHE_PATH)


def _member_cache_for_room(room_id: str, *, day: str) -> list[dict]:
    with _member_cache_lock:
        store = _load_member_cache_file()
    room_rows = store.get(room_id, {})
    return [
        msg
        for msg in room_rows.values()
        if msg.get("day") == day and not msg.get("is_bot")
    ]


def _member_cache_for_range(room_id: str, *, since: date, until: date) -> list[dict]:
    with _member_cache_lock:
        store = _load_member_cache_file()
    room_rows = store.get(room_id, {})
    since_s, until_s = since.isoformat(), until.isoformat()
    return [
        msg
        for msg in room_rows.values()
        if not msg.get("is_bot")
        and since_s <= (msg.get("day") or "") <= until_s
    ]


def _persist_member_messages(
    room_id: str, messages: list[dict], *, zone_name: str, fallback_day: str
) -> None:
    members = [m for m in messages if not m.get("is_bot")]
    if not members:
        return
    zone = tz(zone_name)
    with _member_cache_lock:
        store = _load_member_cache_file()
        room_rows = dict(store.get(room_id, {}))
        for msg in members:
            event_id = msg.get("event_id") or msg.get("id")
            if not event_id:
                continue
            day = fallback_day
            sent = msg.get("sent_at")
            if sent:
                try:
                    day = datetime.fromisoformat(sent).astimezone(zone).date().isoformat()
                except ValueError:
                    pass
            room_rows[str(event_id)] = {**msg, "day": day}
        store[room_id] = room_rows
        _save_member_cache_file(store)


def merge_member_cache(
    room_id: str,
    messages: list[dict],
    *,
    zone_name: str,
    since: date | None = None,
    until: date | None = None,
) -> list[dict]:
    """Merge persisted member messages so the feed survives flaky E2EE decrypt."""
    if since and until:
        cached = _member_cache_for_range(room_id, since=since, until=until)
    else:
        zone = tz(zone_name)
        day = datetime.now(zone).date().isoformat()
        cached = _member_cache_for_room(room_id, day=day)
    if not cached:
        return messages

    by_id = {str(m.get("id") or m.get("event_id")): m for m in messages if m.get("id") or m.get("event_id")}
    for msg in cached:
        key = str(msg.get("id") or msg.get("event_id"))
        if key and key not in by_id:
            by_id[key] = msg
    merged = list(by_id.values())
    merged.sort(key=lambda m: m.get("sent_at") or "")
    return _dedupe_bot_repeats(merged)


def _event_origin_ms(event: Event) -> int:
    origin_ms = getattr(event, "server_timestamp", 0) or 0
    if not origin_ms and hasattr(event, "source"):
        origin_ms = event.source.get("origin_server_ts", 0) or 0
    return int(origin_ms)


def _message_from_text_event(
    event: RoomMessageText,
    *,
    zone,
    day_start: datetime,
    day_end: datetime,
    bot_user: str,
    mxid_to_name: dict[str, str],
    seen: set[str],
) -> dict | None:
    event_id = getattr(event, "event_id", None) or ""
    body = (event.body or "").strip()
    if not body or event_id in seen:
        return None

    origin_ms = _event_origin_ms(event)
    if not origin_ms:
        return None
    sent_at = datetime.fromtimestamp(origin_ms / 1000, tz=zone)
    if sent_at < day_start or sent_at > day_end:
        return None

    sender = event.sender or ""
    is_bot = sender == bot_user
    if is_bot:
        label = "Daily pairs" if "Pairs Today" in body else "PairFlow bot"
    else:
        label = _display_name(sender, mxid_to_name)
    seen.add(event_id)
    return {
        "id": event_id,
        "kind": "daily_message" if is_bot and "Pairs Today" in body else "room_message",
        "label": label,
        "sender": sender,
        "text": body,
        "sent_at": sent_at.isoformat(),
        "is_bot": is_bot,
        "event_id": event_id,
    }


def _reader_configured() -> bool:
    return bool(settings.matrix_room_reader_token.strip())


def _reader_device_id() -> str:
    return settings.matrix_room_reader_device_id.strip() or "PAIRFLOW_READER"


def _reader_store_path(device_id: str) -> Path:
    base = Path(settings.matrix_e2ee_store_path)
    return base / f"reader_{device_id}"


def _build_reader_client(token: str, device_id: str, user_id: str):
    from app.services.matrix_client import _homeserver
    from app.services.matrix_e2ee import _store_class
    from nio import AsyncClient, AsyncClientConfig

    store_path = _reader_store_path(device_id)
    store_path.mkdir(parents=True, exist_ok=True)
    cfg = AsyncClientConfig(
        encryption_enabled=True,
        pickle_key=e2ee_passphrase(),
        store=_store_class(),
        store_name="pairflow.db",
        store_sync_tokens=True,
    )
    client = AsyncClient(
        _homeserver(),
        user_id,
        store_path=str(store_path),
        config=cfg,
    )
    client.restore_login(user_id, device_id, token)
    return client, store_path


async def _resolve_reader_user_id(token: str) -> str:
    import httpx
    from app.services.matrix_client import _homeserver

    r = httpx.get(
        f"{_homeserver()}/_matrix/client/v3/account/whoami",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    r.raise_for_status()
    return r.json()["user_id"]


async def _fetch_messages_async(
    *,
    room_id: str,
    token: str,
    device_id: str,
    zone_name: str,
    mxid_to_name: dict[str, str],
    session_warm: bool,
    range_start: date,
    range_end: date,
    force_keys: bool = False,
) -> list[dict]:
    bot_user = settings.matrix_bot_username
    zone = tz(zone_name)
    fallback_day = datetime.now(zone).date().isoformat()
    day_start = datetime.combine(range_start, dt_time.min, tzinfo=zone)
    day_end = datetime.combine(range_end, dt_time.max, tzinfo=zone)
    span_days = (range_end - range_start).days + 1
    max_pages = 3 if span_days <= 1 else min(20, 4 + span_days)

    use_reader = _reader_configured() and room_id == settings.matrix_room_id
    if use_reader:
        reader_token = settings.matrix_room_reader_token.strip()
        reader_device = _reader_device_id()
        reader_user = await _resolve_reader_user_id(reader_token)
        client, store_path = _build_reader_client(reader_token, reader_device, reader_user)
        session_warm = False
        force_keys = True
    else:
        client, store_path = _build_client(token, device_id)
    store_warm = _is_store_warm(store_path) or session_warm
    try:
        if store_warm and not force_keys:
            await _light_sync(client, room_id)
            if room_id not in client.rooms:
                await _ensure_room_ready(
                    client,
                    room_id,
                    store_path=store_path,
                    session_warm=True,
                    force_keys=False,
                )
        else:
            await _ensure_room_ready(
                client,
                room_id,
                store_path=store_path,
                session_warm=store_warm,
                force_keys=force_keys,
            )
        out: list[dict] = []
        seen: set[str] = set()
        pending_megolm: list[MegolmEvent] = []
        page_from: str | None = None
        page_limit = 80

        for _ in range(max_pages):
            resp = await client.room_messages(
                room_id, start=page_from, limit=page_limit, direction="b"
            )
            if not resp.chunk:
                break

            reached_before_range = False
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
                    origin_ms = _event_origin_ms(event)
                    if not origin_ms:
                        continue
                    sent_at = datetime.fromtimestamp(origin_ms / 1000, tz=zone)
                    if sent_at < day_start:
                        reached_before_range = True
                        continue
                    if sent_at > day_end:
                        continue
                    event_id = getattr(event, "event_id", None) or ""
                    if event_id and event_id not in seen:
                        pending_megolm.append(event)

            page_from = resp.end
            if reached_before_range or not page_from:
                break

        if pending_megolm:
            from app.services.matrix_e2ee import recover_megolm_events

            recovered = await recover_megolm_events(
                client, room_id, pending_megolm, max_rounds=5 if span_days > 1 else 3
            )
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
            if not recovered:
                logger.info(
                    "Room feed: %d encrypted member event(s) still pending in %s",
                    len(pending_megolm),
                    room_id,
                )

        out.sort(key=lambda m: m["sent_at"] or "")
        out = _dedupe_bot_repeats(out)
        _persist_member_messages(
            room_id, out, zone_name=zone_name, fallback_day=fallback_day
        )
        return merge_member_cache(
            room_id,
            out,
            zone_name=zone_name,
            since=range_start if span_days > 1 else None,
            until=range_end if span_days > 1 else None,
        )
    finally:
        await client.close()


async def _fetch_today_async(
    *,
    room_id: str,
    token: str,
    device_id: str,
    zone_name: str,
    mxid_to_name: dict[str, str],
    session_warm: bool,
    force_keys: bool = False,
) -> list[dict]:
    zone = tz(zone_name)
    today = datetime.now(zone).date()
    return await _fetch_messages_async(
        room_id=room_id,
        token=token,
        device_id=device_id,
        zone_name=zone_name,
        mxid_to_name=mxid_to_name,
        session_warm=session_warm,
        range_start=today,
        range_end=today,
        force_keys=force_keys,
    )


def _blocking_fetch(
    *,
    room_id: str,
    zone_name: str,
    mxid_to_name: dict[str, str],
    range_start: date | None = None,
    range_end: date | None = None,
    force_keys: bool = False,
) -> list[dict]:
    sess = get_session()
    store_path = Path(e2ee_store_for_device(sess.device_id))
    session_warm = (
        sess.device_id in _warmed_devices
        or room_id in _cache
        or _is_store_warm(store_path)
    )
    zone = tz(zone_name)
    today = datetime.now(zone).date()
    start = range_start or today
    end = range_end or today
    span_days = (end - start).days + 1
    timeout = 45.0 if span_days <= 1 else (180.0 if span_days > 7 else 120.0)
    with _fetch_lock:
        with _warm_lock:
            rows = _run_fetch_isolated(
                _fetch_messages_async(
                    room_id=room_id,
                    token=sess.access_token,
                    device_id=sess.device_id,
                    zone_name=zone_name,
                    mxid_to_name=mxid_to_name,
                    session_warm=session_warm,
                    range_start=start,
                    range_end=end,
                    force_keys=force_keys,
                ),
                timeout=timeout,
            )
            _warmed_devices.add(sess.device_id)
    rows = merge_member_cache(
        room_id,
        rows,
        zone_name=zone_name,
        since=start if span_days > 1 else None,
        until=end if span_days > 1 else None,
    )
    if rows:
        _cache[room_id] = (time.monotonic(), rows)
    else:
        cached_members = merge_member_cache(
            room_id,
            [],
            zone_name=zone_name,
            since=start if span_days > 1 else None,
            until=end if span_days > 1 else None,
        )
        if cached_members:
            _cache[room_id] = (time.monotonic(), cached_members)
        else:
            _cache.pop(room_id, None)
    return rows if rows else merge_member_cache(
        room_id,
        [],
        zone_name=zone_name,
        since=start if span_days > 1 else None,
        until=end if span_days > 1 else None,
    )


def _background_refresh(
    *,
    room_id: str,
    zone_name: str,
    mxid_to_name: dict[str, str],
    range_start: date | None = None,
    range_end: date | None = None,
) -> None:
    try:
        rows = _blocking_fetch(
            room_id=room_id,
            zone_name=zone_name,
            mxid_to_name=mxid_to_name,
            range_start=range_start,
            range_end=range_end,
        )
        if feed_incomplete(rows):
            keyed = _blocking_fetch(
                room_id=room_id,
                zone_name=zone_name,
                mxid_to_name=mxid_to_name,
                range_start=range_start,
                range_end=range_end,
                force_keys=True,
            )
            if keyed and not feed_incomplete(keyed):
                rows = keyed
            elif keyed and len(keyed) > len(rows):
                rows = keyed
        logger.info("Matrix feed refreshed for %s (%d msgs)", room_id, len(rows))
        from app.services import analysis_service

        analysis_service.invalidate_cache()
        try:
            from app.db.session import SessionLocal
            from app.services import dashboard_service
            from app.services.feed_hub import notify_feed_update

            db = SessionLocal()
            try:
                notify_feed_update(dashboard_service.build_feed(db), force=True)
            finally:
                db.close()
        except Exception:
            logger.debug("Feed WS notify skipped", exc_info=True)
    except Exception:
        logger.exception("Background Matrix feed refresh failed for %s", room_id)
    finally:
        _refreshing.discard(room_id)


def schedule_refresh(
    *,
    room_id: str,
    zone_name: str,
    mxid_to_name: dict[str, str],
    force: bool = False,
    range_start: date | None = None,
    range_end: date | None = None,
) -> bool:
    """Kick off background refresh if not already running. Returns True if scheduled."""
    if not room_id or room_id in _refreshing:
        return False
    age = cache_age(room_id)
    if not force and age is not None and age < _CACHE_TTL:
        return False
    _refreshing.add(room_id)
    threading.Thread(
        target=_background_refresh,
        kwargs={
            "room_id": room_id,
            "zone_name": zone_name,
            "mxid_to_name": mxid_to_name,
            "range_start": range_start,
            "range_end": range_end,
        },
        daemon=True,
        name=f"matrix-feed-{room_id[:8]}",
    ).start()
    return True


def resolve_task_messages(
    *,
    room_id: str,
    zone_name: str,
    mxid_to_name: dict[str, str],
    range_start: date,
    range_end: date,
) -> list[dict]:
    """Task-room feed: in-memory cache + persisted month cache (always merged)."""
    if not room_id:
        return []
    cached = peek_cached(room_id) or []
    merged = merge_member_cache(
        room_id,
        cached,
        zone_name=zone_name,
        since=range_start,
        until=range_end,
    )
    if merged:
        return merged
    try:
        return fetch_task_month_messages(
            room_id=room_id,
            zone_name=zone_name,
            mxid_to_name=mxid_to_name,
            stale_ok=False,
            block=True,
        )
    except Exception:
        logger.exception("Task room month fetch failed for %s", room_id)
        return merged


def fetch_today_messages(
    *,
    room_id: str,
    zone_name: str,
    mxid_to_name: dict[str, str],
    stale_ok: bool = True,
    block: bool = True,
) -> list[dict]:
    """Today's decrypted m.text messages — cache-first, optional non-blocking."""
    return fetch_messages(
        room_id=room_id,
        zone_name=zone_name,
        mxid_to_name=mxid_to_name,
        stale_ok=stale_ok,
        block=block,
    )


def fetch_task_month_messages(
    *,
    room_id: str,
    zone_name: str,
    mxid_to_name: dict[str, str],
    stale_ok: bool = True,
    block: bool = True,
) -> list[dict]:
    """This month's task-room messages for AI context."""
    zone = tz(zone_name)
    start, end = month_bounds(datetime.now(zone).date())
    return fetch_messages(
        room_id=room_id,
        zone_name=zone_name,
        mxid_to_name=mxid_to_name,
        range_start=start,
        range_end=end,
        stale_ok=stale_ok,
        block=block,
    )


def fetch_task_week_messages(
    *,
    room_id: str,
    zone_name: str,
    mxid_to_name: dict[str, str],
    stale_ok: bool = True,
    block: bool = True,
) -> list[dict]:
    """Backward-compatible alias — uses the current month."""
    return fetch_task_month_messages(
        room_id=room_id,
        zone_name=zone_name,
        mxid_to_name=mxid_to_name,
        stale_ok=stale_ok,
        block=block,
    )


def fetch_messages(
    *,
    room_id: str,
    zone_name: str,
    mxid_to_name: dict[str, str],
    range_start: date | None = None,
    range_end: date | None = None,
    stale_ok: bool = True,
    block: bool = True,
) -> list[dict]:
    """Decrypted m.text messages for a date range — cache-first."""
    if not room_id:
        return []

    zone = tz(zone_name)
    today = datetime.now(zone).date()
    start = range_start or today
    end = range_end or today
    span_days = (end - start).days + 1

    now = time.monotonic()
    cached = _cache.get(room_id)
    if cached:
        age = now - cached[0]
        if age < _CACHE_TTL:
            return merge_member_cache(
                room_id,
                list(cached[1]),
                zone_name=zone_name,
                since=start if span_days > 1 else None,
                until=end if span_days > 1 else None,
            )
        if stale_ok:
            schedule_refresh(
                room_id=room_id,
                zone_name=zone_name,
                mxid_to_name=mxid_to_name,
                range_start=start if span_days > 1 else None,
                range_end=end if span_days > 1 else None,
            )
            return merge_member_cache(
                room_id,
                list(cached[1]),
                zone_name=zone_name,
                since=start if span_days > 1 else None,
                until=end if span_days > 1 else None,
            )

    if not block:
        schedule_refresh(
            room_id=room_id,
            zone_name=zone_name,
            mxid_to_name=mxid_to_name,
            range_start=start if span_days > 1 else None,
            range_end=end if span_days > 1 else None,
        )
        return []

    try:
        return _blocking_fetch(
            room_id=room_id,
            zone_name=zone_name,
            mxid_to_name=mxid_to_name,
            range_start=start,
            range_end=end,
        )
    except Exception:
        logger.exception("Matrix room feed fetch failed")
        if cached:
            return merge_member_cache(
                room_id,
                list(cached[1]),
                zone_name=zone_name,
                since=start if span_days > 1 else None,
                until=end if span_days > 1 else None,
            )
        return merge_member_cache(
            room_id,
            [],
            zone_name=zone_name,
            since=start if span_days > 1 else None,
            until=end if span_days > 1 else None,
        )


def fetch_rooms_parallel(
    *,
    room_ids: list[str],
    zone_name: str,
    mxid_to_name: dict[str, str],
    stale_ok: bool = True,
    block: bool = True,
) -> dict[str, list[dict]]:
    ids = [r for r in room_ids if r]
    if not ids:
        return {}

    if not block:
        out: dict[str, list[dict]] = {}
        for rid in ids:
            cached = peek_cached(rid)
            if cached is not None:
                out[rid] = cached
            else:
                out[rid] = []
                schedule_refresh(room_id=rid, zone_name=zone_name, mxid_to_name=mxid_to_name)
        return out

    out: dict[str, list[dict]] = {}
    for rid in ids:
        out[rid] = fetch_today_messages(
            room_id=rid,
            zone_name=zone_name,
            mxid_to_name=mxid_to_name,
            stale_ok=stale_ok,
            block=True,
        )
    return out


def refreshing_rooms() -> list[str]:
    return list(_refreshing)


def prefetch_all(*, zone_name: str, mxid_to_name: dict[str, str]) -> None:
    """Warm message cache for all configured rooms (startup background)."""
    pairing = settings.matrix_room_id
    task = settings.matrix_task_room_id.strip()
    if pairing:
        schedule_refresh(room_id=pairing, zone_name=zone_name, mxid_to_name=mxid_to_name)
    if task:
        zone = tz(zone_name)
        start, end = month_bounds(datetime.now(zone).date())
        schedule_refresh(
            room_id=task,
            zone_name=zone_name,
            mxid_to_name=mxid_to_name,
            range_start=start,
            range_end=end,
        )
