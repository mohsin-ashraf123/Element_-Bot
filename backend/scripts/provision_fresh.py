"""Provision a BRAND-NEW bot device and cross-sign it cleanly.

A fresh device_id avoids the stuck / invalid signature problem on the existing
device (matrix.org won't let us overwrite an existing device signature, and
device deletion via CS API is disabled behind MAS).

Usage:  python -m scripts.provision_fresh NEWDEVICEID
Prints the new device_id + access token to put in .env when successful.
"""

import asyncio
import base64
import copy
import json
import shutil
import sys
import time
from pathlib import Path

import httpx
import nacl.signing
from nacl.encoding import RawEncoder
from nio import AsyncClient, AsyncClientConfig

from app.core.config import settings
from app.services.matrix_client import _homeserver, _parse_mxid
from app.services.matrix_e2ee import _store_class, _sync_filter_for_room
from app.services.matrix_ssss import load_cross_signing_seeds, decode_recovery_key  # noqa: F401

NEW_DEVICE = sys.argv[1] if len(sys.argv) > 1 else "PAIRFLOWBOT"

hs = _homeserver()
uid = settings.matrix_bot_username
room = settings.matrix_room_id
local, _ = _parse_mxid(uid)


def ub64(b: bytes) -> str:
    return base64.b64encode(b).rstrip(b"=").decode()


def b64pad(s: str) -> bytes:
    return base64.b64decode(s + "=" * (-len(s) % 4))


def canonical(obj: dict) -> bytes:
    o = copy.deepcopy(obj)
    o.pop("signatures", None)
    o.pop("unsigned", None)
    return json.dumps(o, sort_keys=True, separators=(",", ":")).encode()


def password_login(device_id: str) -> dict:
    r = httpx.post(
        f"{hs}/_matrix/client/v3/login",
        json={
            "type": "m.login.password",
            "identifier": {"type": "m.id.user", "user": local},
            "password": settings.matrix_bot_password,
            "device_id": device_id,
            "initial_device_display_name": "PairFlow Bot",
        },
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


async def run():
    store_root = Path(settings.matrix_e2ee_store_path)
    store_path = store_root / NEW_DEVICE
    if store_path.exists():
        shutil.rmtree(store_path, ignore_errors=True)
    store_path.mkdir(parents=True, exist_ok=True)

    login = password_login(NEW_DEVICE)
    token = login["access_token"]
    device_id = login["device_id"]
    print(f"[1] logged in — device_id={device_id}")
    H = {"Authorization": f"Bearer {token}"}

    cfg = AsyncClientConfig(
        encryption_enabled=True,
        pickle_key=settings.matrix_pickle_key.strip() or "DEFAULT_KEY",
        store=_store_class(),
        store_name="pairflow.db",
        store_sync_tokens=True,
    )
    client = AsyncClient(hs, uid, store_path=str(store_path), config=cfg)
    try:
        client.restore_login(uid, device_id, token)
        print("    should_upload_keys:", client.should_upload_keys)
        await client.sync(timeout=15000, full_state=True, sync_filter=_sync_filter_for_room(room))
        if client.should_upload_keys:
            await client.keys_upload()
            print("[2] device keys uploaded")
    finally:
        await client.close()

    time.sleep(2)
    r = httpx.post(
        f"{hs}/_matrix/client/v3/keys/query",
        headers=H,
        json={"device_keys": {uid: [device_id]}},
        timeout=20,
    )
    dinfo = r.json().get("device_keys", {}).get(uid, {}).get(device_id)
    if not dinfo:
        print("[3] ABORT — server has no keys for new device")
        return
    print("[3] server has device keys")

    seeds = load_cross_signing_seeds()
    sk = nacl.signing.SigningKey(seeds["self_signing"], encoder=RawEncoder)
    ss_pub = ub64(sk.verify_key.encode(encoder=RawEncoder))
    ss_key_id = f"ed25519:{ss_pub}"

    msg = canonical(dinfo)
    sig = ub64(sk.sign(msg).signature)

    existing = dict(dinfo.get("signatures", {}).get(uid, {}))
    existing[ss_key_id] = sig
    signed = copy.deepcopy(dinfo)
    signed["signatures"] = {uid: existing}

    r2 = httpx.post(
        f"{hs}/_matrix/client/v3/keys/signatures/upload",
        headers=H,
        json={uid: {device_id: signed}},
        timeout=20,
    )
    print("[4] signature upload:", r2.status_code, r2.json().get("failures", {}) or "none")

    r3 = httpx.post(
        f"{hs}/_matrix/client/v3/keys/query", headers=H, json={"device_keys": {uid: []}}, timeout=20
    )
    d2 = r3.json()["device_keys"][uid][device_id]
    server_sig = d2.get("signatures", {}).get(uid, {}).get(ss_key_id)
    vk = nacl.signing.VerifyKey(b64pad(ss_pub), encoder=RawEncoder)
    try:
        vk.verify(canonical(d2), b64pad(server_sig))
        ok = server_sig == sig
        print(f"[5] server signature VALID (matches uploaded: {ok})")
        print("\n=== SUCCESS — update .env with: ===")
        print(f"MATRIX_DEVICE_ID={device_id}")
        print(f"MATRIX_ACCESS_TOKEN={token}")
    except Exception as e:
        print("[5] server signature INVALID:", e)


asyncio.run(run())
