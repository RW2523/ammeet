from __future__ import annotations

import base64
import hashlib
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pyotp
from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

_settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(
    subject: str, extra: dict[str, Any] | None = None, token_version: int = 0
) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=_settings.access_token_expire_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(UTC),
        "jti": str(uuid.uuid4()),
        "type": "access",
        "tv": token_version,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, _settings.secret_key, algorithm=ALGORITHM)


def create_refresh_token(subject: str, token_version: int = 0) -> str:
    expire = datetime.now(UTC) + timedelta(days=_settings.refresh_token_expire_days)
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(UTC),
        "jti": str(uuid.uuid4()),
        "type": "refresh",
        "tv": token_version,
    }
    return jwt.encode(payload, _settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, _settings.secret_key, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise ValueError("Invalid or expired token") from exc


def validate_password_strength(password: str) -> list[str]:
    """Return a list of policy violations; empty list means the password is acceptable."""
    problems: list[str] = []
    if len(password) < _settings.password_min_length:
        problems.append(f"must be at least {_settings.password_min_length} characters")
    if not re.search(r"[a-z]", password):
        problems.append("must contain a lowercase letter")
    if not re.search(r"[A-Z]", password):
        problems.append("must contain an uppercase letter")
    if not re.search(r"\d", password):
        problems.append("must contain a digit")
    return problems


# --- purpose-scoped tokens for email verification / password reset ---

def create_action_token(subject: str, purpose: str, expires_minutes: int = 60 * 24) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=expires_minutes)
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(UTC),
        "jti": str(uuid.uuid4()),
        "type": purpose,
    }
    return jwt.encode(payload, _settings.secret_key, algorithm=ALGORITHM)


def decode_action_token(token: str, purpose: str) -> str:
    """Decode a purpose-scoped token and return the subject. Raises ValueError on any mismatch."""
    return decode_action_token_payload(token, purpose)[0]


def decode_action_token_payload(token: str, purpose: str) -> tuple[str, str]:
    """Decode a purpose-scoped token, returning (subject, jti). Raises ValueError on mismatch."""
    payload = decode_token(token)
    if payload.get("type") != purpose:
        raise ValueError("Wrong token type")
    subject = payload.get("sub")
    if not subject:
        raise ValueError("Missing subject")
    return subject, payload.get("jti", "")


# --- encryption at rest for integration tokens ---

def _fernet() -> Fernet:
    if _settings.token_encryption_key:
        key = _settings.token_encryption_key.encode()
    else:
        # Derive a stable key from secret_key so dev works without extra config
        key = base64.urlsafe_b64encode(hashlib.sha256(_settings.secret_key.encode()).digest())
    return Fernet(key)


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise ValueError("Cannot decrypt stored token (encryption key changed?)") from exc


def generate_totp_secret() -> str:
    return pyotp.random_base32()


def get_totp_uri(secret: str, email: str) -> str:
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name="AmMeeting")


def verify_totp(secret: str, code: str) -> bool:
    totp = pyotp.TOTP(secret)
    return totp.verify(code, valid_window=1)
