"""Security primitives: password hashing, secret encryption and JWTs.

- Passwords: Argon2 via passlib (NFR-4).
- Secrets at rest: Fernet symmetric encryption keyed by SECRETS_ENCRYPTION_KEY.
- Auth tokens: short-lived JWTs signed with SESSION_SECRET.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from cryptography.fernet import Fernet, InvalidToken
from passlib.context import CryptContext

from app.core.config import settings

_pwd = CryptContext(schemes=["argon2"], deprecated="auto")
_JWT_ALG = "HS256"


# ── Passwords ────────────────────────────────────────────
def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


# ── Secret encryption (at rest) ──────────────────────────
def _fernet() -> Fernet:
    key = settings.secrets_encryption_key
    if not key:
        raise RuntimeError("SECRETS_ENCRYPTION_KEY is not configured")
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as exc:  # pragma: no cover - defensive
        raise ValueError("could not decrypt secret (wrong key?)") from exc


# ── JWT access tokens ────────────────────────────────────
def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.access_token_expire_minutes
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, settings.session_secret, algorithm=_JWT_ALG)


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, settings.session_secret, algorithms=[_JWT_ALG])
        return payload.get("sub")
    except jwt.PyJWTError:
        return None
