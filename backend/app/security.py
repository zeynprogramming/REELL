"""Password hashing, JWT handling and login throttling (Phase 4).

Passwords use scrypt from the Python standard library (no extra dependency).
Access tokens are short-lived HS256 JWTs signed with SECRET_KEY.
"""
import base64
import hashlib
import hmac
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import jwt

ALGORITHM = "HS256"
_N, _R, _P, _DKLEN = 2**14, 8, 1, 32
_MAXMEM = 64 * 1024 * 1024
MIN_SECRET_LENGTH = 32
MIN_PASSWORD_LENGTH = 10


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(data: str) -> bytes:
    return base64.b64decode(data.encode("ascii"))


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN, maxmem=_MAXMEM)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored_hash.split("$")
        if scheme != "scrypt":
            return False
        expected = _unb64(digest)
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=_unb64(salt), n=int(n), r=int(r), p=int(p),
            dklen=len(expected), maxmem=_MAXMEM,
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


_dummy_hash: str | None = None


def dummy_hash() -> str:
    """Hash checked when the account does not exist, so response timing does not reveal valid emails."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = hash_password(base64.b64encode(os.urandom(12)).decode())
    return _dummy_hash


def get_secret_key() -> str:
    key = os.getenv("SECRET_KEY", "")
    if len(key) < MIN_SECRET_LENGTH:
        raise RuntimeError(
            "SECRET_KEY is missing or too short (minimum 32 characters). "
            "Generate one with: python3 -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    return key


def access_token_minutes() -> int:
    try:
        return max(1, int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")))
    except ValueError:
        return 60


def create_access_token(user_id: int, token_version: int) -> tuple[str, int]:
    minutes = access_token_minutes()
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user_id), "tv": token_version, "iat": now, "exp": now + timedelta(minutes=minutes)}
    return jwt.encode(payload, get_secret_key(), algorithm=ALGORITHM), minutes * 60


def decode_access_token(token: str) -> dict:
    """Raises jwt.PyJWTError for an invalid, tampered or expired token."""
    payload = jwt.decode(token, get_secret_key(), algorithms=[ALGORITHM], options={"require": ["exp", "sub"]})
    if "purpose" in payload:  # download links must never work as sign-in tokens
        raise jwt.InvalidTokenError("Not an access token")
    return payload


DOWNLOAD_TTL_SECONDS = 300


def create_download_token(recording_id: int, attachment: bool) -> tuple[str, int]:
    """Short-lived, single-recording link token so <video>/<a> can fetch a file without an Authorization header."""
    now = datetime.now(timezone.utc)
    payload = {"purpose": "download", "rid": recording_id, "att": attachment, "iat": now, "exp": now + timedelta(seconds=DOWNLOAD_TTL_SECONDS)}
    return jwt.encode(payload, get_secret_key(), algorithm=ALGORITHM), DOWNLOAD_TTL_SECONDS


def decode_download_token(token: str) -> dict:
    payload = jwt.decode(token, get_secret_key(), algorithms=[ALGORITHM], options={"require": ["exp", "rid"]})
    if payload.get("purpose") != "download":
        raise jwt.InvalidTokenError("Not a download token")
    return payload


class LoginThrottle:
    """In-memory sliding-window limiter for failed sign-ins.

    State is per API process and is lost on restart. Use a shared store (Redis, Phase 6)
    if the API is ever run with several workers.
    """

    def __init__(self, max_attempts: int, window_seconds: int, clock=time.monotonic):
        self.max_attempts = max_attempts
        self.window = window_seconds
        self.clock = clock
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> list[float]:
        hits = [t for t in self._hits.get(key, []) if now - t < self.window]
        if hits:
            self._hits[key] = hits
        else:
            self._hits.pop(key, None)
        return hits

    def retry_after(self, key: str) -> int:
        """Seconds until another attempt is allowed; 0 when not blocked."""
        with self._lock:
            now = self.clock()
            hits = self._prune(key, now)
            if len(hits) < self.max_attempts:
                return 0
            return max(1, int(self.window - (now - hits[0])) + 1)

    def register_failure(self, key: str) -> None:
        with self._lock:
            now = self.clock()
            self._prune(key, now)
            self._hits.setdefault(key, []).append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._hits.pop(key, None)


email_throttle = LoginThrottle(max_attempts=5, window_seconds=15 * 60)
ip_throttle = LoginThrottle(max_attempts=20, window_seconds=15 * 60)
