import os
os.environ.setdefault("SECRET_KEY", "test-secret-key-test-secret-key-0123456789")

import jwt
import pytest
from app import security

def test_hash_and_verify():
    stored = security.hash_password("correct-horse-battery")
    assert stored.startswith("scrypt$") and "correct-horse" not in stored
    assert security.verify_password("correct-horse-battery", stored)
    assert not security.verify_password("wrong", stored)
    assert security.hash_password("correct-horse-battery") != stored  # random salt

def test_verify_rejects_malformed_hash():
    assert not security.verify_password("x", "garbage")
    assert not security.verify_password("x", "bcrypt$1$2$3$4$5")

def test_token_roundtrip_and_tamper():
    token, expires_in = security.create_access_token(7, 3)
    assert expires_in > 0
    payload = security.decode_access_token(token)
    assert payload["sub"] == "7" and payload["tv"] == 3
    with pytest.raises(jwt.PyJWTError):
        security.decode_access_token(token[:-2] + ("AA" if token[-2:] != "AA" else "BB"))

def test_expired_token_rejected(monkeypatch):
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1")
    token = jwt.encode({"sub": "1", "tv": 0, "exp": 1}, os.environ["SECRET_KEY"], algorithm="HS256")
    with pytest.raises(jwt.ExpiredSignatureError):
        security.decode_access_token(token)

def test_none_algorithm_rejected():
    forged = jwt.encode({"sub": "1", "tv": 0, "exp": 9999999999}, key="", algorithm="none")
    with pytest.raises(jwt.PyJWTError):
        security.decode_access_token(forged)

def test_weak_secret_fails_closed(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "short")
    with pytest.raises(RuntimeError):
        security.get_secret_key()

def test_throttle_window():
    now = [0.0]
    t = security.LoginThrottle(max_attempts=3, window_seconds=60, clock=lambda: now[0])
    for _ in range(3):
        assert t.retry_after("k") == 0
        t.register_failure("k")
    assert t.retry_after("k") > 0
    now[0] = 61
    assert t.retry_after("k") == 0
    t.register_failure("k"); t.reset("k")
    assert t.retry_after("k") == 0
