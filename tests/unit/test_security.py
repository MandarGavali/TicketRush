from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_is_salted_and_verifiable():
    first = hash_password("password123")
    second = hash_password("password123")
    assert first != second  # random salt
    assert "password123" not in first
    assert verify_password("password123", first)
    assert not verify_password("wrong-password", first)


def test_token_round_trip():
    token = create_access_token(42, "USER")
    payload = decode_access_token(token)
    assert payload["sub"] == "42"
    assert payload["role"] == "USER"


def test_expired_token_is_rejected():
    long_ago = datetime.now(UTC) - timedelta(minutes=settings.jwt_expire_minutes + 1)
    token = create_access_token(42, "USER", now=long_ago)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_tampered_token_is_rejected():
    header, payload, signature = create_access_token(42, "USER").split(".")
    forged_payload = jwt.utils.base64url_encode(b'{"sub":"1","role":"ADMIN"}').decode()
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(f"{header}.{forged_payload}.{signature}")


def test_token_signed_with_another_secret_is_rejected():
    token = jwt.encode({"sub": "42"}, "some-other-secret-that-is-long-enough", algorithm="HS256")
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(token)


def test_unsigned_alg_none_token_is_rejected():
    token = jwt.encode({"sub": "42", "role": "ADMIN"}, key=None, algorithm="none")
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token)
