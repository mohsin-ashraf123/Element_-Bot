"""Matrix Client-Server API client — login, session reuse, send messages.

Uses a stable device_id so repeated health checks do not create new Matrix
devices (matrix.org hard device limit). Persists the session to disk after a
successful login.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def _data_dir() -> Path:
    return Path(settings.matrix_e2ee_store_path).resolve().parent


def _session_path() -> Path:
    return _data_dir() / "matrix_session.json"


@dataclass
class MatrixSession:
    access_token: str
    device_id: str
    user_id: str


_session: MatrixSession | None = None
_session_checked_at: float = 0.0


def _parse_mxid(mxid: str) -> tuple[str, str]:
    if not mxid.startswith("@"):
        raise ValueError("invalid Matrix user id")
    local, _, server = mxid[1:].partition(":")
    if not local or not server:
        raise ValueError("invalid Matrix user id")
    return local, server


def is_configured() -> bool:
    return bool(
        settings.matrix_homeserver_url.strip()
        and settings.matrix_bot_username.strip()
        and settings.matrix_room_id.strip()
        and (settings.matrix_bot_password.strip() or settings.matrix_access_token.strip())
    )


def _homeserver() -> str:
    """Client-Server API base URL (matrix.org, not element web URL)."""
    url = settings.matrix_homeserver_url.rstrip("/")
    if "matrix-client.matrix.org" in url:
        return "https://matrix.org"
    return url


def e2ee_store_for_device(device_id: str) -> str:
    """Per-device E2EE store — new access token / device gets a fresh store."""
    base = Path(settings.matrix_e2ee_store_path)
    return str(base / device_id)


def e2ee_passphrase() -> str:
    """Passphrase for the on-disk E2EE store (pickle key or recovery key)."""
    if settings.matrix_pickle_key.strip():
        return settings.matrix_pickle_key.strip()
    rk = settings.matrix_recovery_key.replace(" ", "").strip()
    if rk:
        return rk
    return "DEFAULT_KEY"


def _room_label(room_id: str) -> str:
    if not room_id:
        return "—"
    if len(room_id) <= 14:
        return room_id
    return f"{room_id[:5]}…{room_id[-12:]}"


def fetch_room_display_name(sess: MatrixSession, room_id: str) -> str | None:
    """Human-readable room name from Matrix state (m.room.name)."""
    if not room_id:
        return None
    enc = quote(room_id, safe="")
    headers = {"Authorization": f"Bearer {sess.access_token}"}
    with httpx.Client(timeout=12.0) as client:
        r = client.get(
            f"{_homeserver()}/_matrix/client/v3/rooms/{enc}/state/m.room.name",
            headers=headers,
        )
        if r.status_code == 200:
            name = (r.json().get("name") or "").strip()
            if name:
                return name
        r = client.get(
            f"{_homeserver()}/_matrix/client/v3/rooms/{enc}/state/m.room.canonical_alias",
            headers=headers,
        )
        if r.status_code == 200:
            alias = (r.json().get("alias") or "").strip()
            if alias:
                return alias
    return None


def _parse_matrix_error(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        errcode = body.get("errcode", "")
        msg = body.get("error", resp.text)
        if errcode == "M_FORBIDDEN" and "device limit" in msg.lower():
            return (
                "Matrix device limit reached — open Element → Settings → Sessions "
                "and sign out old devices, then retry."
            )
        if errcode == "M_FORBIDDEN" and "password" in msg.lower():
            return f"Invalid bot password ({errcode})"
        return f"{msg} ({errcode or resp.status_code})"
    except Exception:
        return f"Matrix API error ({resp.status_code})"


def _load_persisted_session() -> MatrixSession | None:
    path = _session_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return MatrixSession(
            access_token=data["access_token"],
            device_id=data["device_id"],
            user_id=data["user_id"],
        )
    except (json.JSONDecodeError, KeyError, OSError):
        return None


def _persist_session(session: MatrixSession) -> None:
    path = _session_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "access_token": session.access_token,
                "device_id": session.device_id,
                "user_id": session.user_id,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def _validate_token(client: httpx.Client, token: str) -> bool:
    r = client.get(
        f"{_homeserver()}/_matrix/client/v3/account/whoami",
        headers={"Authorization": f"Bearer {token}"},
    )
    return r.status_code == 200


def _hydrate_session(client: httpx.Client, sess: MatrixSession) -> MatrixSession | None:
    if not _validate_token(client, sess.access_token):
        return None
    r = client.get(
        f"{_homeserver()}/_matrix/client/v3/account/whoami",
        headers={"Authorization": f"Bearer {sess.access_token}"},
    )
    if r.status_code == 200:
        sess.device_id = r.json().get("device_id", sess.device_id)
        sess.user_id = r.json().get("user_id", sess.user_id)
    return sess


def invalidate_session() -> None:
    """Drop cached tokens so the next call re-validates or password-logs in."""
    global _session, _session_checked_at
    _session = None
    _session_checked_at = 0.0


def _is_auth_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(
        token in msg
        for token in (
            "m_unknown_token",
            "unknown token",
            "token is not active",
            "unauthorized",
            "401",
            "m_missing_token",
        )
    )


def get_session(*, force_login: bool = False) -> MatrixSession:
    """Return a valid Matrix session.

    Token order (no manual .env updates needed):
    1. Valid in-memory cache (re-checked on each call after TTL)
    2. ``data/matrix_session.json`` from the last password login
    3. Optional ``MATRIX_ACCESS_TOKEN`` bootstrap in .env
    4. Password login with stable ``MATRIX_DEVICE_ID`` → persist to disk
    """
    global _session, _session_checked_at

    now = time.monotonic()

    with httpx.Client(timeout=15.0) as client:
        if not force_login:
            candidates: list[MatrixSession | None] = [
                _session,
                _load_persisted_session(),
            ]
            if settings.matrix_access_token.strip():
                candidates.append(
                    MatrixSession(
                        access_token=settings.matrix_access_token.strip(),
                        device_id=settings.matrix_device_id,
                        user_id=settings.matrix_bot_username,
                    )
                )
            for cand in candidates:
                if not cand:
                    continue
                hydrated = _hydrate_session(client, cand)
                if hydrated:
                    _session = hydrated
                    _session_checked_at = now
                    _persist_session(hydrated)
                    return hydrated

        if not settings.matrix_bot_password.strip():
            raise RuntimeError(
                "Matrix login failed — set MATRIX_BOT_PASSWORD in .env "
                "(MATRIX_ACCESS_TOKEN is optional and auto-refreshed via password login)"
            )

        localpart, _ = _parse_mxid(settings.matrix_bot_username)
        login = client.post(
            f"{_homeserver()}/_matrix/client/v3/login",
            json={
                "type": "m.login.password",
                "identifier": {"type": "m.id.user", "user": localpart},
                "password": settings.matrix_bot_password,
                "device_id": settings.matrix_device_id,
                "initial_device_display_name": "PairFlow Bot",
            },
        )
        if login.status_code != 200:
            raise RuntimeError(_parse_matrix_error(login))

        data = login.json()
        _session = MatrixSession(
            access_token=data["access_token"],
            device_id=data.get("device_id", settings.matrix_device_id),
            user_id=data.get("user_id", settings.matrix_bot_username),
        )
        _session_checked_at = now
        _persist_session(_session)
        return _session


def ensure_joined_room(session: MatrixSession | None = None) -> bool:
    """Join configured rooms if the bot is not already a member."""
    sess = session or get_session()
    ensure_room_joined(settings.matrix_room_id, sess)
    task = settings.matrix_task_room_id.strip()
    if task:
        ensure_room_joined(task, sess)
    return True


def ensure_room_joined(room_id: str, session: MatrixSession | None = None) -> bool:
    """Join a single room if the bot is not already a member."""
    if not room_id:
        return False
    sess = session or get_session()
    if room_id in joined_rooms(sess):
        return True

    enc = quote(room_id, safe="")
    with httpx.Client(timeout=20.0) as client:
        r = client.post(
            f"{_homeserver()}/_matrix/client/v3/join/{enc}",
            headers={"Authorization": f"Bearer {sess.access_token}"},
            json={},
        )
        if r.status_code in (200, 201):
            return True
        if r.status_code == 403:
            raise RuntimeError(
                f"Bot is not in room {room_id} — invite the bot in Element, then retry"
            )
        raise RuntimeError(_parse_matrix_error(r))


def joined_rooms(session: MatrixSession | None = None) -> list[str]:
    sess = session or get_session()
    with httpx.Client(timeout=12.0) as client:
        r = client.get(
            f"{_homeserver()}/_matrix/client/v3/joined_rooms",
            headers={"Authorization": f"Bearer {sess.access_token}"},
        )
        if r.status_code != 200:
            raise RuntimeError(_parse_matrix_error(r))
        return r.json().get("joined_rooms", [])


def send_text(text: str, *, room_id: str | None = None) -> str:
    """Send a message; uses E2EE when the room is encrypted."""
    target = room_id or settings.matrix_room_id
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            sess = get_session(force_login=attempt > 0)
            ensure_joined_room(sess)

            from app.services import matrix_e2ee

            if matrix_e2ee._is_room_encrypted(target, sess.access_token):
                event_id = matrix_e2ee.try_send_encrypted(
                    text,
                    room_id=target,
                    token=sess.access_token,
                    device_id=sess.device_id,
                )
                if not event_id:
                    raise RuntimeError("Encrypted send returned no event id")
                return event_id

            enc = quote(target, safe="")
            txn_id = f"pairflow-{int(time.time() * 1000)}"
            with httpx.Client(timeout=20.0) as client:
                r = client.put(
                    f"{_homeserver()}/_matrix/client/v3/rooms/{enc}/send/m.room.message/{txn_id}",
                    headers={"Authorization": f"Bearer {sess.access_token}"},
                    json={"msgtype": "m.text", "body": text},
                )
                if r.status_code not in (200, 201):
                    raise RuntimeError(_parse_matrix_error(r))
                return r.json().get("event_id", txn_id)
        except Exception as exc:
            last_exc = exc
            if attempt == 0 and _is_auth_error(exc):
                invalidate_session()
                continue
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError("Matrix send failed")


def send_image(
    png: bytes,
    *,
    room_id: str | None = None,
    filename: str = "weekly-report.png",
    width: int,
    height: int,
) -> str:
    """Upload and send a PNG to the room (E2EE when the room is encrypted)."""
    target = room_id or settings.matrix_room_id
    sess = get_session()
    ensure_joined_room(sess)

    from app.services import matrix_e2ee

    if matrix_e2ee._is_room_encrypted(target, sess.access_token):
        return matrix_e2ee.try_send_encrypted_image(
            png,
            room_id=target,
            token=sess.access_token,
            device_id=sess.device_id,
            filename=filename,
            width=width,
            height=height,
        ) or ""

    # Unencrypted fallback — upload via HTTP then send m.image
    with httpx.Client(timeout=60.0) as client:
        up = client.post(
            f"{_homeserver()}/_matrix/media/v3/upload",
            headers={
                "Authorization": f"Bearer {sess.access_token}",
                "Content-Type": "image/png",
            },
            content=png,
        )
        if up.status_code not in (200, 201):
            raise RuntimeError(_parse_matrix_error(up))
        mxc = up.json().get("content_uri", "")
        enc = quote(target, safe="")
        txn_id = f"pairflow-img-{int(time.time() * 1000)}"
        r = client.put(
            f"{_homeserver()}/_matrix/client/v3/rooms/{enc}/send/m.room.message/{txn_id}",
            headers={"Authorization": f"Bearer {sess.access_token}"},
            json={
                "msgtype": "m.image",
                "body": filename,
                "url": mxc,
                "info": {
                    "mimetype": "image/png",
                    "size": len(png),
                    "w": width,
                    "h": height,
                },
            },
        )
        if r.status_code not in (200, 201):
            raise RuntimeError(_parse_matrix_error(r))
        return r.json().get("event_id", txn_id)


def health_check(*, force: bool = False) -> dict:
    """Connectivity probe for dashboard / room status."""
    base = {
        "configured": is_configured(),
        "connected": False,
        "joined": False,
        "e2ee_store_ready": False,
        "homeserver": _homeserver(),
        "room_id": settings.matrix_room_id or None,
        "room_label": _room_label(settings.matrix_room_id),
        "error": None,
        "cached": False,
    }

    if not base["configured"]:
        base["error"] = "Matrix env vars incomplete"
        return base

    try:
        sess = get_session(force_login=force)
        base["connected"] = True
        base["device_id"] = sess.device_id
    except Exception as exc:
        base["error"] = str(exc)
        return base

    try:
        ensure_joined_room(sess)
        joined = joined_rooms(sess)
        base["joined"] = settings.matrix_room_id in joined
        task_id = settings.matrix_task_room_id.strip() or None
        base["task_room_id"] = task_id
        base["task_room_label"] = _room_label(task_id) if task_id else None
        base["task_room_joined"] = task_id in joined if task_id else None
        if not base["joined"]:
            try:
                ensure_room_joined(settings.matrix_room_id, sess)
                joined = joined_rooms(sess)
                base["joined"] = settings.matrix_room_id in joined
            except Exception as join_exc:
                logger.warning("Pairing room join retry failed: %s", join_exc)
        if task_id and not base.get("task_room_joined"):
            try:
                ensure_room_joined(task_id, sess)
                joined = joined_rooms(sess)
                base["task_room_joined"] = task_id in joined
            except Exception as join_exc:
                logger.warning("Task room join retry failed: %s", join_exc)
        store = Path(e2ee_store_for_device(sess.device_id))
        base["e2ee_store_ready"] = store.exists() and bool(
            settings.matrix_pickle_key or settings.matrix_recovery_key
        )
        display = fetch_room_display_name(sess, settings.matrix_room_id)
        if display:
            base["room_name"] = display
            base["room_label"] = display
        if task_id:
            task_display = fetch_room_display_name(sess, task_id)
            if task_display:
                base["task_room_name"] = task_display
                base["task_room_label"] = task_display
        if not base["joined"]:
            base["error"] = "Bot logged in but not joined to pairing room — invite the bot"
        elif task_id and not base["task_room_joined"]:
            base["error"] = "Bot not joined to task room — invite the bot to the task room"
    except Exception as exc:
        base["error"] = str(exc)

    if "room_name" not in base:
        base["room_name"] = None
    if "task_room_name" not in base:
        base["task_room_name"] = None

    return base
