"""Element Secret Storage (SSSS / 4S) helpers.

matrix-nio does not support server-side secret storage, so we implement the
minimal parts needed to recover cross-signing private keys from the account's
recovery key. This lets the PairFlow bot self-sign its own device with the
*real* self-signing key, so other clients (which already trust the account's
master key) stop showing "unknown / unverified device" warnings.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from urllib.parse import quote

import base58
import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.core.config import settings
from app.services.matrix_client import _homeserver, get_session

logger = logging.getLogger(__name__)

_RECOVERY_PREFIX = bytes([0x8B, 0x01])
_KEY_SIZE = 32


def decode_recovery_key(recovery_key: str) -> bytes:
    """Base58-decode an Element recovery key into the 32-byte SSSS secret."""
    raw = base58.b58decode(recovery_key.replace(" ", "").strip())

    parity = 0
    for b in raw:
        parity ^= b
    if parity != 0:
        raise ValueError("Recovery key parity check failed")
    if raw[: len(_RECOVERY_PREFIX)] != _RECOVERY_PREFIX:
        raise ValueError("Recovery key prefix invalid")
    if len(raw) != len(_RECOVERY_PREFIX) + _KEY_SIZE + 1:
        raise ValueError("Recovery key length invalid")

    return bytes(raw[len(_RECOVERY_PREFIX) : len(_RECOVERY_PREFIX) + _KEY_SIZE])


def _hkdf(ikm: bytes, info: str, length: int = 64) -> bytes:
    salt = bytes(32)
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    okm = b""
    prev = b""
    counter = 1
    while len(okm) < length:
        prev = hmac.new(prk, prev + info.encode("utf-8") + bytes([counter]), hashlib.sha256).digest()
        okm += prev
        counter += 1
    return okm[:length]


def _aes_ctr(key: bytes, iv: bytes, data: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.CTR(iv))
    dec = cipher.decryptor()
    return dec.update(data) + dec.finalize()


def verify_ssss_key(ssss_key: bytes, descriptor: dict) -> bool:
    """Check a candidate SSSS key against the stored key descriptor MAC."""
    keys = _hkdf(ssss_key, "", 64)
    aes_key, mac_key = keys[:32], keys[32:]

    iv = base64.b64decode(descriptor["iv"])
    ciphertext = _aes_ctr(aes_key, iv, bytes(32))
    expected_mac = hmac.new(mac_key, ciphertext, hashlib.sha256).digest()
    return hmac.compare_digest(
        base64.b64encode(expected_mac).decode().rstrip("="),
        descriptor["mac"].rstrip("="),
    )


def decrypt_secret(ssss_key: bytes, name: str, encrypted: dict) -> bytes:
    """Decrypt an SSSS secret; returns the raw secret bytes (ed25519 seed)."""
    keys = _hkdf(ssss_key, name, 64)
    aes_key, mac_key = keys[:32], keys[32:]

    iv = base64.b64decode(encrypted["iv"])
    ciphertext = base64.b64decode(encrypted["ciphertext"])
    mac = base64.b64decode(encrypted["mac"] + "==")

    calc_mac = hmac.new(mac_key, ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(calc_mac, mac):
        raise ValueError(f"MAC mismatch decrypting {name}")

    plaintext = _aes_ctr(aes_key, iv, ciphertext)
    # Cross-signing secrets are stored as unpadded base64 of the 32-byte seed.
    return base64.b64decode(plaintext.decode("ascii") + "==")


def _account_data(client: httpx.Client, token: str, user_id: str, dtype: str) -> dict | None:
    uenc = quote(user_id, safe="")
    r = client.get(
        f"{_homeserver()}/_matrix/client/v3/user/{uenc}/account_data/{dtype}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    return r.json() if r.status_code == 200 else None


def load_cross_signing_seeds(session=None) -> dict:
    """Recover cross-signing ed25519 seeds from SSSS using the recovery key.

    Returns {"self_signing": bytes, "master": bytes, "user_signing": bytes}.
    """
    if not settings.matrix_recovery_key.strip():
        raise RuntimeError("MATRIX_RECOVERY_KEY is not set in .env")

    sess = session or get_session()
    user_id = settings.matrix_bot_username
    ssss_key = decode_recovery_key(settings.matrix_recovery_key)

    with httpx.Client() as client:
        default = _account_data(client, sess.access_token, user_id, "m.secret_storage.default_key")
        if not default:
            raise RuntimeError("No default secret storage key on the account")
        key_id = default["key"]
        descriptor = _account_data(
            client, sess.access_token, user_id, f"m.secret_storage.key.{key_id}"
        )
        if not descriptor or not verify_ssss_key(ssss_key, descriptor):
            raise RuntimeError(
                "Recovery key does not match the account's secret storage — "
                "check MATRIX_RECOVERY_KEY"
            )

        seeds: dict[str, bytes] = {}
        for name, short in [
            ("m.cross_signing.self_signing", "self_signing"),
            ("m.cross_signing.master", "master"),
            ("m.cross_signing.user_signing", "user_signing"),
        ]:
            data = _account_data(client, sess.access_token, user_id, name)
            if data and key_id in data.get("encrypted", {}):
                seeds[short] = decrypt_secret(ssss_key, name, data["encrypted"][key_id])

    if "self_signing" not in seeds:
        raise RuntimeError("Self-signing key not found in secret storage")
    return seeds
