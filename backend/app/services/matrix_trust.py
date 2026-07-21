"""Matrix device trust diagnostics and cross-signing helpers."""

from __future__ import annotations

import base64
import copy
import json
import logging
from dataclasses import dataclass

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.config import settings
from app.services.matrix_client import MatrixSession, _homeserver, get_session

logger = logging.getLogger(__name__)


def _unpadded_b64(data: bytes) -> str:
    return base64.b64encode(data).rstrip(b"=").decode("ascii")


def _sign_json(private_key: Ed25519PrivateKey, obj: dict) -> str:
    payload = copy.deepcopy(obj)
    payload.pop("signatures", None)
    payload.pop("unsigned", None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _unpadded_b64(private_key.sign(canonical))


@dataclass
class DeviceStatus:
    device_id: str
    display_name: str | None
    has_keys: bool
    cross_signed: bool


def _query_keys(client: httpx.Client, token: str, user_id: str) -> dict:
    r = client.post(
        f"{_homeserver()}/_matrix/client/v3/keys/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"device_keys": {user_id: []}},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def _list_devices(client: httpx.Client, token: str) -> list[dict]:
    r = client.get(
        f"{_homeserver()}/_matrix/client/v3/devices",
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    )
    r.raise_for_status()
    return r.json().get("devices", [])


def _device_cross_signed(device_info: dict, user_id: str, device_id: str) -> bool:
    sigs = device_info.get("signatures", {}).get(user_id, {})
    return any(k.startswith("ed25519:") and k != f"ed25519:{device_id}" for k in sigs)


def diagnose(session: MatrixSession | None = None) -> dict:
    """Return why other clients may show 'unknown device' for the bot."""
    sess = session or get_session()
    user_id = settings.matrix_bot_username

    with httpx.Client(timeout=20) as client:
        devices = _list_devices(client, sess.access_token)
        keys = _query_keys(client, sess.access_token, user_id)
        keyed = keys.get("device_keys", {}).get(user_id, {})

    rows: list[DeviceStatus] = []
    ghost_ids: list[str] = []
    unsigned_ids: list[str] = []

    for dev in devices:
        did = dev["device_id"]
        info = keyed.get(did)
        has_keys = info is not None
        cross_signed = _device_cross_signed(info, user_id, did) if info else False
        rows.append(
            DeviceStatus(
                device_id=did,
                display_name=dev.get("display_name"),
                has_keys=has_keys,
                cross_signed=cross_signed,
            )
        )
        if not has_keys:
            ghost_ids.append(did)
        elif not cross_signed:
            unsigned_ids.append(did)

    has_master = user_id in keys.get("master_keys", {})
    current = next((r for r in rows if r.device_id == sess.device_id), None)

    alerts: list[str] = []
    if ghost_ids:
        alerts.append(
            f"Ghost sessions (no keys): {', '.join(ghost_ids)} — "
            "sign these out in Element → Settings → Sessions on @bot_dtrader"
        )
    if unsigned_ids:
        alerts.append(f"Unsigned devices: {', '.join(unsigned_ids)}")
    if current and not current.cross_signed:
        alerts.append(f"Current PairFlow device {sess.device_id} is not cross-signed")

    return {
        "user_id": user_id,
        "current_device_id": sess.device_id,
        "cross_signing_configured": has_master,
        "devices": [
            {
                "device_id": r.device_id,
                "display_name": r.display_name,
                "has_keys": r.has_keys,
                "cross_signed": r.cross_signed,
                "is_current": r.device_id == sess.device_id,
            }
            for r in rows
        ],
        "ghost_device_ids": ghost_ids,
        "unsigned_device_ids": unsigned_ids,
        "trust_ok": not ghost_ids and not unsigned_ids and bool(current and current.cross_signed),
        "alerts": alerts,
        "fix_steps": _fix_steps(ghost_ids, sess.device_id),
    }


def _fix_steps(ghost_ids: list[str], current_device: str) -> list[str]:
    steps = [
        "Log into Element as @bot_dtrader (not your personal account).",
        "Open Settings → Security → Sessions.",
        f"Keep only the current PairFlow session ({current_device} / PairFlow Bot).",
    ]
    if ghost_ids:
        steps.append(f"Sign out ghost sessions: {', '.join(ghost_ids)}.")
    steps.extend(
        [
            "Sign out old Element browser/Windows sessions if you do not need them.",
            "Send a new test message from PairFlow — the red warning should disappear.",
            "If it persists on your account, open chatbot → Verify session once.",
        ]
    )
    return steps


def ensure_current_device_signed(session: MatrixSession | None = None) -> dict:
    """Cross-sign the active PairFlow device using the account's REAL self-signing key.

    The self-signing key is recovered from Element Secret Storage (SSSS) using
    MATRIX_RECOVERY_KEY, so the signature chains to the account's existing
    master key that other clients already trust. This is safe and idempotent —
    it never generates a new cross-signing identity.
    """
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from app.services.matrix_ssss import load_cross_signing_seeds

    sess = session or get_session()
    user_id = settings.matrix_bot_username

    with httpx.Client(timeout=30) as client:
        keys = _query_keys(client, sess.access_token, user_id)
        device_info = keys.get("device_keys", {}).get(user_id, {}).get(sess.device_id)
        if not device_info:
            raise RuntimeError(
                f"Device {sess.device_id} has no uploaded keys — send one E2EE message first"
            )

        if _device_cross_signed(device_info, user_id, sess.device_id):
            return {"signed": False, "message": f"Device {sess.device_id} already cross-signed"}

        seeds = load_cross_signing_seeds(sess)
        ss_priv = Ed25519PrivateKey.from_private_bytes(seeds["self_signing"])
        ss_pub = _unpadded_b64(ss_priv.public_key().public_bytes_raw())
        ss_key_id = f"ed25519:{ss_pub}"

        device_sig = _sign_json(ss_priv, device_info)
        existing = dict(device_info.get("signatures", {}).get(user_id, {}))
        existing[ss_key_id] = device_sig
        signed_device = copy.deepcopy(device_info)
        signed_device["signatures"] = {user_id: existing}

        r = client.post(
            f"{_homeserver()}/_matrix/client/v3/keys/signatures/upload",
            headers={"Authorization": f"Bearer {sess.access_token}"},
            json={user_id: {sess.device_id: signed_device}},
            timeout=30,
        )
        if r.status_code not in (200, 201):
            raise RuntimeError(f"Signature upload failed: {r.text[:300]}")
        failures = r.json().get("failures", {})
        if failures:
            raise RuntimeError(f"Signature upload rejected: {failures}")

        logger.info("Cross-signed PairFlow device %s with real self-signing key", sess.device_id)
        return {"signed": True, "message": f"Device {sess.device_id} cross-signed"}


def run_trust_check() -> dict:
    """On startup: ensure the current device is cross-signed, then diagnose."""
    try:
        result = ensure_current_device_signed()
        logger.info("Matrix self-sign: %s", result.get("message"))
    except Exception as exc:
        logger.warning("Matrix self-sign skipped: %s", exc)

    try:
        report = diagnose()
        for alert in report.get("alerts", []):
            logger.warning("Matrix trust: %s", alert)
        if report.get("trust_ok"):
            logger.info("Matrix device trust OK for %s", report["current_device_id"])
        return report
    except Exception as exc:
        logger.warning("Matrix trust check skipped: %s", exc)
        return {"trust_ok": False, "error": str(exc)}
