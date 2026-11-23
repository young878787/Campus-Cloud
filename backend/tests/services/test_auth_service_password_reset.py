"""app/services/user/auth_service.py 的密碼重設與忘記密碼：版本已過期的 token 與 LDAP 帳號不可重設，同一連結只能成功一次。"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from app.exceptions import BadRequestError
from app.services.user import auth_service
from app.utils.token import generate_password_reset_token

_USER_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# password reset token is single-use via token_version binding
# ---------------------------------------------------------------------------


def test_reset_password_rejects_token_issued_before_version_bump(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(
        id=_USER_ID,
        email="user@example.com",
        token_version=4,
        is_active=True,
        auth_source="local",
    )
    monkeypatch.setattr(
        auth_service.user_repo, "get_user_by_email", lambda *, session, email: user
    )
    stale_token = generate_password_reset_token(email=user.email, token_version=3)

    with pytest.raises(BadRequestError):
        auth_service.reset_password(
            session=SimpleNamespace(), token=stale_token, new_password="N3wPassw0rd!"
        )


def test_reset_password_accepts_current_version_and_bumps_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(
        id=_USER_ID,
        email="user@example.com",
        token_version=4,
        is_active=True,
        auth_source="local",
    )
    monkeypatch.setattr(
        auth_service.user_repo, "get_user_by_email", lambda *, session, email: user
    )

    def _fake_update_user(*, session: Any, db_user: Any, user_in: Any) -> Any:
        # 比照 user_repo.update_user：帶密碼就把 token_version +1
        if "password" in user_in.model_dump(exclude_unset=True):
            db_user.token_version += 1
        return db_user

    monkeypatch.setattr(auth_service.user_repo, "update_user", _fake_update_user)
    monkeypatch.setattr(
        auth_service.audit_service, "log_action", lambda **kwargs: None
    )
    session = SimpleNamespace(add=lambda obj: None, commit=lambda: None)
    token = generate_password_reset_token(email=user.email, token_version=4)

    auth_service.reset_password(session=session, token=token, new_password="N3wPassw0rd!")
    assert user.token_version == 5

    # 同一個連結第二次使用必須失敗
    with pytest.raises(BadRequestError):
        auth_service.reset_password(
            session=session, token=token, new_password="An0therPass!"
        )


# ---------------------------------------------------------------------------
# LDAP 帳號不得走本地密碼（登入 / 忘記密碼 / 重設）
# ---------------------------------------------------------------------------


def test_recover_password_sends_no_email_for_ldap_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[Any] = []
    user = SimpleNamespace(
        id=_USER_ID, email="ldap@example.com", token_version=0, auth_source="ldap"
    )
    monkeypatch.setattr(
        auth_service.user_repo, "get_user_by_email", lambda *, session, email: user
    )
    monkeypatch.setattr(
        auth_service.audit_service, "log_action", lambda **kwargs: None
    )
    monkeypatch.setattr(auth_service, "send_email", lambda **kwargs: sent.append(kwargs))

    auth_service.recover_password(session=SimpleNamespace(), email=user.email)

    assert sent == []


def test_reset_password_rejects_ldap_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(
        id=_USER_ID,
        email="ldap@example.com",
        token_version=0,
        is_active=True,
        auth_source="ldap",
    )
    monkeypatch.setattr(
        auth_service.user_repo, "get_user_by_email", lambda *, session, email: user
    )
    token = generate_password_reset_token(email=user.email, token_version=0)

    with pytest.raises(BadRequestError):
        auth_service.reset_password(
            session=SimpleNamespace(), token=token, new_password="N3wPassw0rd!"
        )
