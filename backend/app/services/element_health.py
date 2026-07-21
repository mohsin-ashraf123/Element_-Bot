"""Lightweight Matrix connectivity check — delegates to matrix_client."""

from __future__ import annotations

import copy
import logging
import threading
import time

from app.services import matrix_client

logger = logging.getLogger(__name__)

_CACHE_TTL_OK = 120.0
_CACHE_TTL_ERR = 45.0
_STALE_OK_MAX = 600.0

_cache: dict | None = None
_cache_expires: float = 0.0
_last_ok: dict | None = None
_last_ok_at: float = 0.0
_cache_fingerprint: str = ""
_refreshing = False
_refresh_lock = threading.Lock()


def is_configured() -> bool:
    return matrix_client.is_configured()


def _fingerprint() -> str:
    from app.core.config import settings

    return (
        f"{settings.matrix_bot_username}:{settings.matrix_device_id}:"
        f"{settings.matrix_room_id}:{settings.matrix_task_room_id}"
    )


def _env_fallback() -> dict:
    """Instant status from env — no Matrix network (never blocks API threads)."""
    from app.core.config import settings

    configured = matrix_client.is_configured()
    return {
        "configured": configured,
        "connected": False,
        "joined": False,
        "e2ee_store_ready": False,
        "homeserver": matrix_client._homeserver() if configured else None,
        "room_id": settings.matrix_room_id or None,
        "room_label": matrix_client._room_label(settings.matrix_room_id),
        "room_name": None,
        "task_room_id": settings.matrix_task_room_id.strip() or None,
        "task_room_label": (
            matrix_client._room_label(settings.matrix_task_room_id.strip())
            if settings.matrix_task_room_id.strip()
            else None
        ),
        "task_room_name": None,
        "task_room_joined": None,
        "error": None if configured else "Matrix env vars incomplete",
        "cached": True,
        "checking": True,
    }


def _apply_result(result: dict) -> dict:
    global _cache, _cache_expires, _last_ok, _last_ok_at

    now = time.monotonic()
    out = copy.deepcopy(result)
    out.pop("checking", None)

    if result.get("connected") and result.get("joined"):
        _last_ok = copy.deepcopy(out)
        _last_ok_at = now
        ttl = _CACHE_TTL_OK
    elif (
        result.get("error")
        and "429" in str(result.get("error"))
        and _last_ok is not None
        and (now - _last_ok_at) < _STALE_OK_MAX
    ):
        stale = copy.deepcopy(_last_ok)
        stale["cached"] = True
        stale["error"] = result["error"]
        _cache = stale
        _cache_expires = now + _CACHE_TTL_ERR
        return stale
    else:
        ttl = _CACHE_TTL_ERR if result.get("error") else _CACHE_TTL_OK

    _cache = copy.deepcopy(out)
    _cache_expires = now + ttl
    return out


def _refresh_background() -> None:
    global _refreshing

    with _refresh_lock:
        if _refreshing:
            return
        _refreshing = True

    try:
        result = matrix_client.health_check()
        _apply_result(result)
        logger.debug("Matrix health refreshed (connected=%s)", result.get("connected"))
    except Exception as exc:
        logger.warning("Matrix health background refresh failed: %s", exc)
    finally:
        with _refresh_lock:
            _refreshing = False


def _schedule_refresh() -> None:
    threading.Thread(
        target=_refresh_background, daemon=True, name="matrix-health-refresh"
    ).start()


def check(*, force: bool = False) -> dict:
    """Return cached Matrix health instantly; refresh in background when stale."""
    global _cache, _cache_fingerprint

    fp = _fingerprint()
    if fp != _cache_fingerprint:
        _cache = None
        _cache_fingerprint = fp

    now = time.monotonic()

    if force:
        return _apply_result(matrix_client.health_check(force=force))

    if _cache is not None and now < _cache_expires:
        out = copy.deepcopy(_cache)
        out["cached"] = True
        return out

    if _last_ok is not None and (now - _last_ok_at) < _STALE_OK_MAX:
        out = copy.deepcopy(_last_ok)
        out["cached"] = True
        _schedule_refresh()
        return out

    if _cache is not None:
        out = copy.deepcopy(_cache)
        out["cached"] = True
        _schedule_refresh()
        return out

    _schedule_refresh()
    return _env_fallback()


