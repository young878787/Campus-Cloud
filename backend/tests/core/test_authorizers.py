"""app/core/authorizers.py 的 require_ai_api_manage 與 app/core/permissions.py 的 AI_API_MANAGE_ALL：檢視全部權限不等於寫入權限，管理員可管理他人的 AI API 金鑰。"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.core.authorizers import require_ai_api_manage
from app.core.permissions import Permission, has_permission
from app.exceptions import PermissionDeniedError
from app.models import UserRole

# ── 2. AI API 金鑰：寫入權限與明文外流 ──────────────────────────────────────


def test_view_all_is_not_a_write_bypass() -> None:
    teacher = SimpleNamespace(id=uuid.uuid4(), role=UserRole.teacher, is_superuser=False)
    assert has_permission(teacher, Permission.AI_API_MANAGE_ALL) is False
    with pytest.raises(PermissionDeniedError):
        require_ai_api_manage(teacher, uuid.uuid4())


def test_admin_may_manage_other_users_credentials() -> None:
    admin = SimpleNamespace(id=uuid.uuid4(), role=UserRole.admin, is_superuser=False)
    assert has_permission(admin, Permission.AI_API_MANAGE_ALL) is True
    require_ai_api_manage(admin, uuid.uuid4())
