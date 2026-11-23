"""SECRET_KEY must be a fixed value."""

from __future__ import annotations

import warnings

import pytest
from pydantic import ValidationError

from app.core.config import Settings

_REQUIRED = {
    "PROJECT_NAME": "SkyLab",
    "POSTGRES_SERVER": "db",
    "POSTGRES_USER": "postgres",
    "POSTGRES_PASSWORD": "a-real-db-password",
    "FIRST_SUPERUSER": "admin@example.com",
    "FIRST_SUPERUSER_PASSWORD": "a-real-admin-password",
    # 非註冊設定測試不應被公開註冊的 Turnstile 前置條件干擾。
    "ENABLE_SIGNUP": False,
}


@pytest.fixture
def no_secret_key_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECRET_KEY", raising=False)


def test_missing_secret_key_rejected_outside_local(no_secret_key_env: None) -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(_env_file=None, ENVIRONMENT="production", **_REQUIRED)  # type: ignore[call-arg]


def test_empty_secret_key_rejected_outside_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # env_ignore_empty turns `SECRET_KEY=` into "unset".
    monkeypatch.setenv("SECRET_KEY", "")
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(_env_file=None, ENVIRONMENT="staging", **_REQUIRED)  # type: ignore[call-arg]


def test_fixed_secret_key_accepted_outside_local(no_secret_key_env: None) -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        s = Settings(  # type: ignore[call-arg]
            _env_file=None,
            ENVIRONMENT="production",
            SECRET_KEY="z" * 43,
            **_REQUIRED,
        )
    assert s.SECRET_KEY == "z" * 43


def test_short_secret_key_only_warns(no_secret_key_env: None) -> None:
    with pytest.warns(UserWarning, match="shorter than 32"):
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            ENVIRONMENT="production",
            SECRET_KEY="short-but-stable",
            **_REQUIRED,
        )


def test_missing_secret_key_only_warns_in_local(no_secret_key_env: None) -> None:
    with pytest.warns(UserWarning, match="SECRET_KEY is not set"):
        Settings(_env_file=None, ENVIRONMENT="local", **_REQUIRED)  # type: ignore[call-arg]


def test_public_signup_requires_complete_turnstile_outside_local() -> None:
    with pytest.raises(ValidationError, match="TURNSTILE_SITE_KEY"):
        Settings(  # type: ignore[call-arg]
            _env_file=None,
            ENVIRONMENT="production",
            SECRET_KEY="z" * 43,
            **{**_REQUIRED, "ENABLE_SIGNUP": True},
        )

    configured = Settings(  # type: ignore[call-arg]
        _env_file=None,
        ENVIRONMENT="production",
        SECRET_KEY="z" * 43,
        TURNSTILE_SITE_KEY="site-key",
        TURNSTILE_SECRET_KEY="secret-key",
        SMTP_HOST="smtp.example.com",
        EMAILS_FROM_EMAIL="noreply@ntub.edu.tw",
        **{**_REQUIRED, "ENABLE_SIGNUP": True},
    )
    assert configured.turnstile_enabled is True


def test_local_signup_can_run_without_turnstile() -> None:
    configured = Settings(  # type: ignore[call-arg]
        _env_file=None,
        ENVIRONMENT="local",
        SECRET_KEY="z" * 43,
        **{**_REQUIRED, "ENABLE_SIGNUP": True},
    )
    assert configured.turnstile_enabled is False
