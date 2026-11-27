"""Bombadil UI 測試的種子資料：只允許寫入本機隔離資料庫。

由 stack.sh 在隔離副本的 backend/ 目錄下執行（PYTHONPATH=.）：
- 標記初始化精靈已完成（否則前端一律導去 /setup）
- 建立 student / teacher 測試帳號（admin 由 initial_data.py 依 FIRST_SUPERUSER 建立），
  三個帳號都標記已完成新手引導（否則整個版面被引導頁取代）
- 先建立第一次讀取才會建立的 singleton（LDAP 設定、全域配額、Web Push VAPID 金鑰），探索時的寫入稽核才能維持嚴格白名單
"""

import os
import sys
from datetime import datetime, timezone

from sqlmodel import Session, select

from app.core.config import settings

EXPECTED_PORT = int(os.environ.get("BOMBADIL_PG_PORT", "55432"))
if settings.POSTGRES_SERVER != "127.0.0.1" or settings.POSTGRES_PORT != EXPECTED_PORT:
    sys.exit(
        f"拒絕：資料庫不是隔離環境（{settings.POSTGRES_SERVER}:{settings.POSTGRES_PORT}）"
    )

from app.core.db import engine  # noqa: E402
from app.models import SystemSetup, User  # noqa: E402
from app.repositories import user as user_repo  # noqa: E402
from app.repositories.ldap_config import get_ldap_config  # noqa: E402
from app.repositories.push import get_web_push_config  # noqa: E402
from app.services.resource.quota_service import get_global_quota  # noqa: E402
from app.repositories.system_setup import SYSTEM_SETUP_ID  # noqa: E402
from app.schemas.user import UserCreate  # noqa: E402

PASSWORD = os.environ.get("BOMBADIL_USER_PASSWORD", "UiTest-Pass-1234")
ACCOUNTS = [
    ("student@example.com", "student", "UI Student"),
    ("teacher@example.com", "teacher", "UI Teacher"),
]

with Session(engine) as session:
    setup = session.get(SystemSetup, SYSTEM_SETUP_ID) or SystemSetup(id=SYSTEM_SETUP_ID)
    setup.completed = True
    setup.completed_at = setup.completed_at or datetime.now(timezone.utc)
    session.add(setup)
    session.commit()
    for email, role, name in ACCOUNTS:
        if session.exec(select(User).where(User.email == email)).first():
            continue
        user_repo.create_user(
            session=session,
            user_create=UserCreate(email=email, password=PASSWORD, role=role, full_name=name),
        )
    session.commit()
    for user in session.exec(select(User)).all():
        user.onboarding_completed = True
        session.add(user)
    session.commit()
    get_ldap_config(session=session)
    get_global_quota(session)
    get_web_push_config(session=session)
    users = session.exec(select(User)).all()
    print("seeded:", sorted((u.email, str(u.role.value)) for u in users))
