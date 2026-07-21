"""Encrypted Matrix message send via matrix-nio."""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
from pathlib import Path

import httpx
from nio import AsyncClient, AsyncClientConfig, RoomSendResponse
from nio.events import Event
from nio.events.room_events import MegolmEvent
from nio.responses import UploadResponse
from nio.crypto.sas import SasState
from nio.exceptions import LocalProtocolError
from nio.responses import JoinedMembersResponse
from nio.store.database import DefaultStore

from app.core.config import settings
from app.services.matrix_client import (
    MatrixSession,
    _homeserver,
    e2ee_passphrase,
    e2ee_store_for_device,
    ensure_joined_room,
)
from app.services.matrix_store_win import WindowsSafeStore

logger = logging.getLogger(__name__)

_WARM_SYNC_TIMEOUT = 5_000
_FULL_SYNC_TIMEOUT = 15_000
_KEY_ROUNDS_COLD = 3
_KEY_ROUNDS_WARM = 1
_warm_lock = threading.Lock()
_warmed_devices: set[str] = set()


def _use_windows_store() -> bool:
    return sys.platform.startswith("win")


def _store_class():
    return WindowsSafeStore if _use_windows_store() else DefaultStore


def _is_room_encrypted(room_id: str, token: str) -> bool:
    hs = _homeserver()
    enc = quote_room(room_id)
    r = httpx.get(
        f"{hs}/_matrix/client/v3/rooms/{enc}/state/m.room.encryption",
        headers={"Authorization": f"Bearer {token}"},
        timeout=12,
    )
    return r.status_code == 200


def quote_room(room_id: str) -> str:
    from urllib.parse import quote

    return quote(room_id, safe="")


def _sync_filter_for_room(room_id: str) -> dict:
    """Only sync the target room — avoids minutes of unrelated-room decryption."""
    return {
        "room": {
            "rooms": [room_id],
            "timeline": {"limit": 50},
            "state": {"lazy_load_members": False},
            "ephemeral": {"lazy_load_members": True},
        }
    }


def _is_store_warm(store_path: Path) -> bool:
    db = store_path / "pairflow.db"
    return db.is_file() and db.stat().st_size > 8_192


async def _flush_outgoing(client: AsyncClient) -> None:
    if client.outgoing_to_device_messages:
        await client.send_to_device_messages()


async def _auto_handle_verifications(client: AsyncClient) -> None:
    """Auto-accept SAS when a user verifies the bot in Element."""
    for txn_id, sas in list(client.key_verifications.items()):
        if sas.canceled or sas.verified or sas.we_started_it:
            continue
        try:
            if sas.state == SasState.created:
                await client.accept_key_verification(txn_id)
                await _flush_outgoing(client)
                logger.info(
                    "Accepted device verification from %s (%s)",
                    sas.other_olm_device.user_id,
                    sas.other_olm_device.id,
                )
        except LocalProtocolError as exc:
            logger.debug("SAS accept skipped for %s: %s", txn_id, exc)

    for txn_id, sas in list(client.key_verifications.items()):
        if sas.canceled or sas.verified or sas.we_started_it:
            continue
        try:
            if sas.other_key_set and not sas.sas_accepted:
                await client.confirm_short_auth_string(txn_id)
                await _flush_outgoing(client)
                logger.info(
                    "Confirmed device verification with %s (%s)",
                    sas.other_olm_device.user_id,
                    sas.other_olm_device.id,
                )
        except LocalProtocolError as exc:
            logger.debug("SAS confirm skipped for %s: %s", txn_id, exc)


async def _ensure_member_keys(
    client: AsyncClient,
    room_id: str,
    *,
    rounds: int,
) -> None:
    joined = await client.joined_members(room_id)
    if not isinstance(joined, JoinedMembersResponse):
        raise RuntimeError("Could not load room members for E2EE setup")

    member_ids = [m.user_id for m in joined.members]
    logger.info("E2EE key setup for %s — members: %s", room_id, member_ids)

    for user_id in member_ids:
        client.olm.users_for_key_query.add(user_id)

    room_filter = _sync_filter_for_room(room_id)
    for _ in range(rounds):
        if client.users_for_key_query:
            try:
                await client.keys_query()
            except LocalProtocolError:
                break
        await client.sync(timeout=_WARM_SYNC_TIMEOUT, sync_filter=room_filter)
        await _auto_handle_verifications(client)
        await _flush_outgoing(client)

    try:
        await client.keys_upload()
    except Exception as exc:
        logger.debug("keys_upload skipped: %s", exc)

    for user_id in member_ids:
        for device in client.device_store.active_user_devices(user_id):
            try:
                with _warm_lock:
                    client.verify_device(device)
            except PermissionError:
                logger.debug("verify_device skipped (store locked): %s %s", user_id, device.id)
            except OSError as exc:
                if getattr(exc, "winerror", None) == 5:
                    logger.debug("verify_device skipped (access denied): %s %s", user_id, device.id)
                else:
                    raise

    await client.sync(timeout=_WARM_SYNC_TIMEOUT, sync_filter=room_filter)
    await _auto_handle_verifications(client)
    await _flush_outgoing(client)


async def recover_megolm_events(
    client: AsyncClient,
    room_id: str,
    pending: list[MegolmEvent],
    *,
    max_rounds: int = 4,
) -> list[Event]:
    """Request missing Megolm keys and retry decrypting undecrypted timeline events."""
    if not pending or not client.olm:
        return []

    room_filter = _sync_filter_for_room(room_id)
    missing = client.get_missing_sessions(room_id)
    if missing:
        try:
            await client.keys_claim(missing)
        except Exception as exc:
            logger.debug("keys_claim during megolm recovery failed: %s", exc)

    for event in pending:
        if event.session_id in client.outgoing_key_requests:
            continue
        try:
            await client.request_room_key(event)
            await _flush_outgoing(client)
        except LocalProtocolError as exc:
            logger.debug("room key request skipped for %s: %s", event.session_id, exc)

    decrypted: list[Event] = []
    still_pending = list(pending)

    for _ in range(max_rounds):
        if not still_pending:
            break
        await client.sync(timeout=10_000, sync_filter=room_filter)
        await _auto_handle_verifications(client)
        await _flush_outgoing(client)

        next_pending: list[MegolmEvent] = []
        for event in still_pending:
            try:
                dec = client.decrypt_event(event)
            except Exception:
                next_pending.append(event)
                continue
            if dec is None or isinstance(dec, MegolmEvent):
                next_pending.append(event)
            else:
                decrypted.append(dec)
        still_pending = next_pending

    if still_pending:
        logger.warning(
            "Megolm recovery left %d undecrypted event(s) in %s",
            len(still_pending),
            room_id,
        )
    return decrypted


async def _bootstrap_e2ee(
    client: AsyncClient,
    room_id: str,
    *,
    warm: bool,
    skip_keys: bool = False,
) -> None:
    room_filter = _sync_filter_for_room(room_id)
    if warm and client.loaded_sync_token:
        await client.sync(timeout=_WARM_SYNC_TIMEOUT, sync_filter=room_filter)
    else:
        await client.sync(
            timeout=_FULL_SYNC_TIMEOUT,
            full_state=True,
            sync_filter=room_filter,
        )

    await _auto_handle_verifications(client)
    await _flush_outgoing(client)

    if not skip_keys:
        await _ensure_member_keys(
            client,
            room_id,
            rounds=_KEY_ROUNDS_WARM if warm else _KEY_ROUNDS_COLD,
        )
    elif room_id not in client.rooms:
        await client.sync(
            timeout=_FULL_SYNC_TIMEOUT,
            full_state=True,
            sync_filter=room_filter,
        )


def _build_client(token: str, device_id: str) -> tuple[AsyncClient, Path]:
    store_cls = _store_class()
    store_path = Path(e2ee_store_for_device(device_id))
    store_path.mkdir(parents=True, exist_ok=True)

    cfg = AsyncClientConfig(
        encryption_enabled=True,
        pickle_key=e2ee_passphrase(),
        store=store_cls,
        store_name="pairflow.db",
        store_sync_tokens=True,
    )
    client = AsyncClient(
        _homeserver(),
        settings.matrix_bot_username,
        store_path=str(store_path),
        config=cfg,
    )
    client.restore_login(settings.matrix_bot_username, device_id, token)
    return client, store_path


async def _light_sync(client: AsyncClient, room_id: str) -> None:
    room_filter = _sync_filter_for_room(room_id)
    await client.sync(timeout=_WARM_SYNC_TIMEOUT, sync_filter=room_filter)
    await _auto_handle_verifications(client)
    await _flush_outgoing(client)


async def _ensure_room_ready(
    client: AsyncClient,
    room_id: str,
    *,
    store_path: Path,
    session_warm: bool,
    force_keys: bool = False,
) -> None:
    store_warm = _is_store_warm(store_path)
    ensure_joined_room(
        MatrixSession(client.access_token, client.device_id, settings.matrix_bot_username)
    )
    await _bootstrap_e2ee(
        client,
        room_id,
        warm=store_warm or session_warm,
        skip_keys=session_warm and not force_keys,
    )
    await _light_sync(client, room_id)
    if room_id not in client.rooms:
        await client.sync(
            timeout=_FULL_SYNC_TIMEOUT,
            full_state=True,
            sync_filter=_sync_filter_for_room(room_id),
        )
    if room_id not in client.rooms:
        # Store may have been warmed on a different room — one full sync loads all joined rooms.
        await client.sync(timeout=_FULL_SYNC_TIMEOUT, full_state=True)
    if room_id not in client.rooms:
        raise RuntimeError(f"Room {room_id} not loaded — retry in a few seconds")


async def _send_encrypted_async(text: str, room_id: str, token: str, device_id: str) -> str:
    client, store_path = _build_client(token, device_id)
    session_warm = device_id in _warmed_devices

    try:
        await _ensure_room_ready(
            client, room_id, store_path=store_path, session_warm=session_warm
        )

        resp = await client.room_send(
            room_id,
            "m.room.message",
            {"msgtype": "m.text", "body": text},
            ignore_unverified_devices=False,
        )
        if isinstance(resp, RoomSendResponse):
            _warmed_devices.add(device_id)
            return resp.event_id
        raise RuntimeError(f"Encrypted send failed: {resp}")
    finally:
        await client.close()


async def _warm_store_async(token: str, device_id: str, room_id: str) -> None:
    client, store_path = _build_client(token, device_id)
    store_warm = _is_store_warm(store_path)
    try:
        ensure_joined_room(MatrixSession(token, device_id, settings.matrix_bot_username))
        await _bootstrap_e2ee(client, room_id, warm=store_warm, skip_keys=False)
        _warmed_devices.add(device_id)
        logger.info("E2EE store warmed for device %s", device_id)
    finally:
        await client.close()


async def _accept_verifications_async(token: str, device_id: str) -> dict:
    """Listen for SAS verification requests and auto-accept (PairFlow = other device)."""
    client, _ = _build_client(token, device_id)
    accepted: list[str] = []
    try:
        for _ in range(12):
            # Full sync — to_device verification events are not room-scoped.
            await client.sync(timeout=10_000)
            before = set(client.key_verifications.keys())
            await _auto_handle_verifications(client)
            await _flush_outgoing(client)
            await client.sync(timeout=5_000)
            await _auto_handle_verifications(client)
            await _flush_outgoing(client)
            after = set(client.key_verifications.keys())
            for txn in after:
                sas = client.key_verifications[txn]
                if sas.verified:
                    accepted.append(txn)
            if accepted:
                break
            if not before and not after:
                continue
        verified = [
            txn
            for txn, sas in client.key_verifications.items()
            if sas.verified
        ]
        return {
            "ok": bool(verified),
            "verified_transactions": verified,
            "pending": [
                txn
                for txn, sas in client.key_verifications.items()
                if not sas.verified and not sas.canceled
            ],
            "message": (
                "Verification accepted by PairFlow bot"
                if verified
                else "No verification request found — click Verify session in Element, then retry within 30 seconds"
            ),
        }
    finally:
        await client.close()


def accept_pending_verifications() -> dict:
    from app.services.matrix_client import get_session

    sess = get_session()
    return asyncio.run(_accept_verifications_async(sess.access_token, sess.device_id))


def warm_store(*, token: str | None = None, device_id: str | None = None) -> None:
    """Pre-warm the E2EE store on startup so the first send is fast."""
    from app.services.matrix_client import get_session

    if not settings.matrix_room_id.strip():
        return

    sess = get_session()
    tok = token or sess.access_token
    dev = device_id or sess.device_id
    rooms = [settings.matrix_room_id]
    task = settings.matrix_task_room_id.strip()
    if task:
        rooms.append(task)

    with _warm_lock:
        if dev in _warmed_devices:
            return
        try:
            for room in rooms:
                asyncio.run(_warm_store_async(tok, dev, room))
        except Exception as exc:
            logger.warning("E2EE warm-up skipped: %s", exc)


def send_encrypted(text: str, *, room_id: str | None = None, token: str, device_id: str) -> str:
    target = room_id or settings.matrix_room_id
    return asyncio.run(_send_encrypted_async(text, target, token, device_id))


async def _send_image_encrypted_async(
    png: bytes,
    *,
    room_id: str,
    token: str,
    device_id: str,
    filename: str = "weekly-report.png",
    width: int,
    height: int,
) -> str:
    client, store_path = _build_client(token, device_id)
    session_warm = device_id in _warmed_devices

    try:
        await _ensure_room_ready(
            client, room_id, store_path=store_path, session_warm=session_warm
        )

        def _provider(_got_429: int, _got_timeouts: int) -> bytes:
            return png

        upload_resp, decrypt_info = await client.upload(
            _provider,
            content_type="image/png",
            filename=filename,
            encrypt=True,
            filesize=len(png),
        )
        if not isinstance(upload_resp, UploadResponse):
            raise RuntimeError(f"Image upload failed: {upload_resp}")

        # Encrypted media: MXC URL + decryption keys live under `file`, not top-level `url`.
        file_info = dict(decrypt_info or {})
        file_info["url"] = upload_resp.content_uri
        file_info["mimetype"] = "image/png"

        content: dict = {
            "msgtype": "m.image",
            "body": filename,
            "file": file_info,
            "info": {
                "mimetype": "image/png",
                "size": len(png),
                "w": width,
                "h": height,
            },
        }

        resp = await client.room_send(
            room_id,
            "m.room.message",
            content,
            ignore_unverified_devices=False,
        )
        if isinstance(resp, RoomSendResponse):
            _warmed_devices.add(device_id)
            return resp.event_id
        raise RuntimeError(f"Encrypted image send failed: {resp}")
    finally:
        await client.close()


def send_encrypted_image(
    png: bytes,
    *,
    room_id: str | None = None,
    token: str,
    device_id: str,
    filename: str = "weekly-report.png",
    width: int,
    height: int,
) -> str:
    target = room_id or settings.matrix_room_id
    return asyncio.run(
        _send_image_encrypted_async(
            png,
            room_id=target,
            token=token,
            device_id=device_id,
            filename=filename,
            width=width,
            height=height,
        )
    )


def try_send_encrypted_image(
    png: bytes,
    *,
    room_id: str | None = None,
    token: str,
    device_id: str,
    filename: str = "weekly-report.png",
    width: int,
    height: int,
) -> str | None:
    try:
        target = room_id or settings.matrix_room_id
        if not _is_room_encrypted(target, token):
            return None
        return send_encrypted_image(
            png,
            room_id=target,
            token=token,
            device_id=device_id,
            filename=filename,
            width=width,
            height=height,
        )
    except Exception as exc:
        logger.warning("E2EE image send failed: %s", exc)
        raise RuntimeError(f"Encrypted image send failed: {exc}") from exc


def try_send_encrypted(text: str, *, room_id: str | None = None, token: str, device_id: str) -> str | None:
    """Return event id on success, None if room is not encrypted."""
    try:
        target = room_id or settings.matrix_room_id
        if not _is_room_encrypted(target, token):
            return None
        return send_encrypted(text, room_id=target, token=token, device_id=device_id)
    except Exception as exc:
        logger.warning("E2EE send failed: %s", exc)
        raise RuntimeError(
            f"Encrypted send failed: {exc}. "
            "In Element: open the bot profile → Verify session (one-time)."
        ) from exc
