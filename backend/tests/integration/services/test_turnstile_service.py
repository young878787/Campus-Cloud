"""Cloudflare Turnstile 機器人驗證：需真 DB 的登入路由接線（password 登入與登入方式清單）。"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.api.deps import TURNSTILE_HEADER
from app.core.config import settings
from app.services.user import turnstile_service

API = settings.API_V1_STR


class _FakeSiteverify:
    """取代 Cloudflare siteverify：記錄呼叫並回傳指定結果（或丟出指定例外）。"""

    def __init__(
        self, result: dict[str, Any] | None = None, exc: Exception | None = None
    ) -> None:
        self.result = result or {"success": True, "action": "login"}
        self.exc = exc
        self.calls: list[dict[str, str]] = []

    async def __call__(self, *, secret: str, token: str) -> dict[str, Any]:
        self.calls.append({"secret": secret, "token": token})
        if self.exc is not None:
            raise self.exc
        return self.result


@pytest.fixture
def enable_turnstile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "TURNSTILE_SITE_KEY", "site-key")
    monkeypatch.setattr(settings, "TURNSTILE_SECRET_KEY", "secret-key")


def _install(monkeypatch: pytest.MonkeyPatch, fake: _FakeSiteverify) -> None:
    monkeypatch.setattr(turnstile_service, "siteverify", fake)


def _superuser_form() -> dict[str, str]:
    return {
        "username": settings.FIRST_SUPERUSER,
        "password": settings.FIRST_SUPERUSER_PASSWORD,
    }


@pytest.mark.usefixtures("enable_turnstile")
def test_password_login_requires_token(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeSiteverify()
    _install(monkeypatch, fake)

    r = client.post(f"{API}/login/access-token", data=_superuser_form())
    assert r.status_code == 400
    assert fake.calls == []

    r = client.post(
        f"{API}/login/access-token",
        data=_superuser_form(),
        headers={TURNSTILE_HEADER: "tok"},
    )
    assert r.status_code == 200
    assert r.json().get("access_token") or r.json().get("totp_required")
    assert fake.calls == [{"secret": "secret-key", "token": "tok"}]


def test_login_methods_exposes_site_key_only_when_enabled(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "TURNSTILE_SITE_KEY", None)
    monkeypatch.setattr(settings, "TURNSTILE_SECRET_KEY", None)
    r = client.get(f"{API}/login/methods")
    assert r.status_code == 200
    assert r.json()["turnstile_site_key"] is None

    monkeypatch.setattr(settings, "TURNSTILE_SITE_KEY", "site-key")
    monkeypatch.setattr(settings, "TURNSTILE_SECRET_KEY", "secret-key")
    r = client.get(f"{API}/login/methods")
    assert r.json()["turnstile_site_key"] == "site-key"
    assert "secret-key" not in r.text
