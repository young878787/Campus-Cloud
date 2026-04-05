from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import engine, init_db
from app.main import app
from app.models import (
    AIAPICredential,
    AIAPIRequest,
    AuditLog,
    FirewallLayout,
    Group,
    GroupMember,
    Resource,
    SpecChangeRequest,
    User,
    VMRequest,
)
from tests.utils.user import authentication_token_from_email
from tests.utils.utils import get_superuser_token_headers


@pytest.fixture(scope="session")
def db() -> Generator[Session, None, None]:
    """
    Session-scoped DB fixture that connects to the real PostgreSQL.

    IMPORTANT: autouse is intentionally set to False (default) so this
    fixture only activates for tests that explicitly declare `db` as a
    parameter. This prevents the teardown logic from running automatically
    and wiping the remote database on every pytest invocation.

    Teardown strategy: instead of DELETE-all on every table, we only
    delete test-created users (non-superusers whose email matches the
    test-user pattern) and their cascading dependent rows. The
    FIRST_SUPERUSER account is always preserved.
    """
    with Session(engine) as session:
        init_db(session)
        yield session
        _cleanup_test_data(session)


def _cleanup_test_data(session: Session) -> None:
    """
    Remove only the data that was created during the test run.

    Rules:
    - Never delete the FIRST_SUPERUSER account.
    - Delete non-superuser test users and their owned rows only.
    - AuditLog is NOT manually deleted: its user_id FK is ondelete=SET NULL,
      so the DB handles nullification automatically when the user is deleted.
      Audit history is preserved intentionally.
    - Only rows whose user_id is explicitly in test_user_ids are deleted,
      avoiding accidental removal of rows with NULL user_id.
    """
    from sqlmodel import col

    # Collect test-created user IDs (everything except the superuser seed account)
    test_users = session.exec(
        select(User).where(User.email != settings.FIRST_SUPERUSER)
    ).all()
    test_user_ids = list({u.id for u in test_users})

    if not test_user_ids:
        return  # Nothing to clean up

    # Models with user_id FK (NOT NULL) — delete rows owned by test users only.
    # AuditLog is excluded: ondelete=SET NULL means DB nullifies user_id automatically.
    user_owned_models: list[type] = [
        FirewallLayout,   # user_id NOT NULL, FK → user.id
        AIAPICredential,  # user_id NOT NULL
        AIAPIRequest,     # user_id NOT NULL
        GroupMember,      # user_id NOT NULL
        SpecChangeRequest,
        VMRequest,
        Resource,
    ]
    for model in user_owned_models:
        rows = session.exec(  # type: ignore[call-overload]
            select(model).where(col(model.user_id).in_(test_user_ids))  # type: ignore[attr-defined]
        ).all()
        for row in rows:
            session.delete(row)
    session.flush()

    # Groups have no user_id; wipe all test-created groups
    groups = session.exec(select(Group)).all()
    for group in groups:
        session.delete(group)
    session.flush()

    # Delete the test users themselves (AuditLog.user_id becomes NULL via DB cascade)
    for user in test_users:
        session.delete(user)

    session.commit()


@pytest.fixture(scope="module")
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def superuser_token_headers(client: TestClient) -> dict[str, str]:
    return get_superuser_token_headers(client)


@pytest.fixture(scope="module")
def normal_user_token_headers(client: TestClient, db: Session) -> dict[str, str]:
    return authentication_token_from_email(
        client=client, email=settings.EMAIL_TEST_USER, db=db
    )
