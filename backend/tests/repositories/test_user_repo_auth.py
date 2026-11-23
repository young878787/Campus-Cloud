"""app/repositories/user.py：LDAP 帳號不得用本地密碼登入；改密碼或停用帳號時 bump token_version，無關變更則保留。"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from app.core import security
from app.models import User
from app.repositories import user as user_repo
from app.schemas import UserUpdate

_USER_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# LDAP 帳號不得走本地密碼（登入 / 忘記密碼 / 重設）
# ---------------------------------------------------------------------------


def test_authenticate_rejects_ldap_account(monkeypatch: pytest.MonkeyPatch) -> None:
    """LDAP 帳號就算本地雜湊恰好對得上，也不能用密碼登入。"""
    password = "Correct-Horse-1"
    ldap_user = SimpleNamespace(
        id=_USER_ID,
        email="ldap@example.com",
        auth_source="ldap",
        hashed_password=security.get_password_hash(password),
    )
    monkeypatch.setattr(
        user_repo, "get_user_by_email", lambda *, session, email: ldap_user
    )

    assert (
        user_repo.authenticate(
            session=SimpleNamespace(), email=ldap_user.email, password=password
        )
        is None
    )


# ---------------------------------------------------------------------------
# 管理員改密碼 / 停用帳號要讓既有 token 失效
# ---------------------------------------------------------------------------


class _FlushSession:
    def add(self, obj: Any) -> None:
        pass

    def flush(self) -> None:
        pass


def _local_user() -> User:
    return User(
        email="user@example.com",
        hashed_password=security.get_password_hash("Old-Passw0rd"),
        token_version=7,
        is_active=True,
    )


def test_update_user_bumps_token_version_on_password_change() -> None:
    user = _local_user()
    user_repo.update_user(
        session=_FlushSession(),
        db_user=user,
        user_in=UserUpdate(password="N3wPassw0rd!"),
    )
    assert user.token_version == 8


def test_update_user_bumps_token_version_on_deactivation() -> None:
    user = _local_user()
    user_repo.update_user(
        session=_FlushSession(), db_user=user, user_in=UserUpdate(is_active=False)
    )
    assert user.token_version == 8


def test_update_user_keeps_token_version_on_unrelated_change() -> None:
    user = _local_user()
    user_repo.update_user(
        session=_FlushSession(), db_user=user, user_in=UserUpdate(full_name="改個名字")
    )
    assert user.token_version == 7


def test_update_user_keeps_token_version_when_already_inactive() -> None:
    user = _local_user()
    user.is_active = False
    user_repo.update_user(
        session=_FlushSession(), db_user=user, user_in=UserUpdate(is_active=False)
    )
    assert user.token_version == 7
