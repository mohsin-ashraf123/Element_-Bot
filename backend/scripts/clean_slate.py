"""Clean-slate E2EE provisioning for the PairFlow bot device.

Wipes local crypto state, does a fresh password login (reusing the fixed
device_id), uploads fresh device keys, verifies the server accepted them,
then cross-signs the device with the account's real self-signing key
(recovered from SSSS via the recovery key).
"""

import asyncio
import base64
import copy
import json
import shutil
import time
from pathlib import Path

import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core.config import settings
from app.services.matrix_client import _homeserver, get_session
from app.services.matrix_e2ee import _build_client, _sync_filter_for_room
from app.services.matrix_ssss import load_cross_signing_seeds

hs = _homeserver()
uid = settings.matrix_bot_username
room = settings.matrix_room_id


def ub64(b: bytes) -> str:
    return base64.b64encode(b).rstrip(b"=").decode()


def wipe():
    store = Path(settings.matrix_e2ee_store_path)
    if store.exists():
        shutil.rmtree(store, ignore_errors=True)
    sess_file = Path("./data/matrix_session.json")
    if sess_file.exists():
        sess_file.unlink()
    print("[1] wiped local crypto store + session")


def sign_json(priv: Ed25519PrivateKey, obj: dict) -> str:
    payload = copy.deepcopy(obj)
    payload.pop("signatures", None)
    payload.pop("unsigned", None)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return ub64(priv.sign(canonical))


async def run():
    wipe()

    sess = get_session(force_login=True)
    H = {"Authorization": f"Bearer {sess.access_token}"}
    print(f"[2] fresh login — device {sess.device_id}")

    client, _ = _build_client(sess.access_token, sess.device_id)
    try:
        print("    should_upload_keys:", client.should_upload_keys)
        print("    local curve:", client.olm.account.identity_keys["curve25519"])

        # Full sync then upload device + one-time keys.
        await client.sync(timeout=15000, full_state=True, sync_filter=_sync_filter_for_room(room))
        if client.should_upload_keys:
            resp = await client.keys_upload()
            print("[3] keys_upload:", type(resp).__name__)
        else:
            print("[3] nio says no upload needed")
    finally:
        await client.close()

    time.sleep(2)
    r = httpx.post(
        f"{hs}/_matrix/client/v3/keys/query",
        headers=H,
        json={"device_keys": {uid: [sess.device_id]}},
        timeout=20,
    )
    info = r.json().get("device_keys", {}).get(uid, {}).get(sess.device_id)
    print("[4] server has keys for device:", info is not None)
    if not info:
        print("    device list:", list(r.json().get("device_keys", {}).get(uid, {}).keys()))
        print("    ABORT — server did not register device keys")
        return

    # Cross-sign with real self-signing key.
    seeds = load_cross_signing_seeds(sess)
    ss_priv = Ed25519PrivateKey.from_private_bytes(seeds["self_signing"])
    ss_pub = ub64(ss_priv.public_key().public_bytes_raw())
    ss_key_id = f"ed25519:{ss_pub}"

    device_sig = sign_json(ss_priv, info)
    existing = dict(info.get("signatures", {}).get(uid, {}))
    existing[ss_key_id] = device_sig
    signed = copy.deepcopy(info)
    signed["signatures"] = {uid: existing}

    r2 = httpx.post(
        f"{hs}/_matrix/client/v3/keys/signatures/upload",
        headers=H,
        json={uid: {sess.device_id: signed}},
        timeout=20,
    )
    failures = r2.json().get("failures", {})
    print("[5] cross-sign upload:", r2.status_code, "failures:", failures or "none")

    # Verify
    r3 = httpx.post(
        f"{hs}/_matrix/client/v3/keys/query", headers=H, json={"device_keys": {uid: []}}, timeout=20
    )
    dk = r3.json().get("device_keys", {}).get(uid, {}).get(sess.device_id, {})
    sigs = dk.get("signatures", {}).get(uid, {})
    cross = any(k.startswith("ed25519:") and k != f"ed25519:{sess.device_id}" for k in sigs)
    print("[6] device cross_signed:", cross)


asyncio.run(run())
