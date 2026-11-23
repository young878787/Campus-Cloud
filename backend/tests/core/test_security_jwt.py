"""Unit tests for JWT creation in app.core.security.

Covers the new ``jti`` claim and ensures backward-compatible ``ver``/``type``
claims remain present.
"""

from __future__ import annotations

from datetime import timedelta

import jwt

from app.core import security
from app.core.config import settings


def _decode(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[security.ALGORITHM])


def test_create_access_token_has_jti_and_type() -> None:
    token = security.create_access_token(
        subject="user-1", expires_delta=timedelta(minutes=5), token_version=3
    )
    payload = _decode(token)

    assert payload["sub"] == "user-1"
    assert payload["type"] == "access"
    assert payload["ver"] == 3
    assert payload["exp"] > 0
    jti = payload["jti"]
    assert isinstance(jti, str) and len(jti) == 32  # uuid4().hex


def test_create_refresh_token_has_distinct_jti_per_call() -> None:
    t1 = security.create_refresh_token("u", expires_delta=timedelta(minutes=5))
    t2 = security.create_refresh_token("u", expires_delta=timedelta(minutes=5))

    assert _decode(t1)["jti"] != _decode(t2)["jti"]
    assert _decode(t1)["type"] == "refresh"


def test_access_and_refresh_token_have_different_types() -> None:
    access = security.create_access_token("u", expires_delta=timedelta(minutes=5))
    refresh = security.create_refresh_token("u", expires_delta=timedelta(minutes=5))

    assert _decode(access)["type"] == "access"
    assert _decode(refresh)["type"] == "refresh"
