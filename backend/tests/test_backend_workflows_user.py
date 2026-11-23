"""Split from tests/test_backend_workflows.py: user roles & template filtering.

Shared fixtures live in tests.ai.teacher_judge.helpers.
"""

from datetime import datetime, timezone

import pytest
from sqlmodel import Session

from app.exceptions import (
    BadRequestError,
)
from app.models import (
    Resource,
    User,
    UserRole,
)
from app.services.user import user_service
from tests.utils.user import create_user_with_role


@pytest.fixture()
def db(sqlite_session: Session) -> Session:
    return sqlite_session


def test_user_role_teacher_is_treated_as_regular_user(db: Session) -> None:
    teacher = create_user_with_role(db, role=UserRole.teacher)

    assert teacher.role == UserRole.teacher
    assert teacher.is_superuser is False


def test_delete_user_rejects_owned_resources(db: Session) -> None:
    owner = create_user_with_role(db)
    admin = create_user_with_role(db, is_superuser=True)
    db.add(
        Resource(
            vmid=999,
            user_id=owner.id,
            environment_type="Owned VM",
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()

    with pytest.raises(BadRequestError):
        user_service.delete_user(session=db, user_id=owner.id, current_user=admin)

    assert db.get(User, owner.id) is not None
