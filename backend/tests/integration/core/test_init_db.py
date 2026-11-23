"""init_db must not restore the .env superuser after setup."""

from __future__ import annotations

import uuid

import pytest
from sqlmodel import Session, select

from app.core import db as core_db
from app.core.config import settings
from app.models import SystemSetup, User
from app.repositories.system_setup import SYSTEM_SETUP_ID


def _set_setup_completed(db: Session, completed: bool | None) -> None:
    state = db.get(SystemSetup, SYSTEM_SETUP_ID)
    if completed is None:
        if state is not None:
            db.delete(state)
    else:
        if state is None:
            state = SystemSetup(id=SYSTEM_SETUP_ID)
        state.completed = completed
        db.add(state)
    db.commit()


@pytest.mark.parametrize(
    ("completed", "expect_created"),
    [(True, False), (False, True), (None, True)],
)
def test_init_db_respects_finished_setup(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    completed: bool | None,
    expect_created: bool,
) -> None:
    email = f"setup-first-{uuid.uuid4().hex[:8]}@example.com"
    monkeypatch.setattr(settings, "FIRST_SUPERUSER", email)
    original = db.get(SystemSetup, SYSTEM_SETUP_ID)
    snapshot = None if original is None else original.model_dump()
    try:
        _set_setup_completed(db, completed)

        core_db.init_db(db)

        user = db.exec(select(User).where(User.email == email)).first()
        assert (user is not None) is expect_created
    finally:
        db.expire_all()
        user = db.exec(select(User).where(User.email == email)).first()
        if user is not None:
            db.delete(user)
            db.commit()
        state = db.get(SystemSetup, SYSTEM_SETUP_ID)
        if snapshot is None:
            if state is not None:
                db.delete(state)
        else:
            if state is None:
                state = SystemSetup(**snapshot)
            else:
                for key, value in snapshot.items():
                    setattr(state, key, value)
            db.add(state)
        db.commit()


def test_ensure_first_superuser_ignores_finished_setup(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Test fixtures rely on this to seed the superuser even on a DB whose
    # setup wizard is already marked completed.
    email = f"setup-ensure-{uuid.uuid4().hex[:8]}@example.com"
    monkeypatch.setattr(settings, "FIRST_SUPERUSER", email)
    original = db.get(SystemSetup, SYSTEM_SETUP_ID)
    snapshot = None if original is None else original.model_dump()
    try:
        _set_setup_completed(db, True)

        core_db.ensure_first_superuser(db)

        user = db.exec(select(User).where(User.email == email)).first()
        assert user is not None
        assert user.is_superuser
    finally:
        db.expire_all()
        user = db.exec(select(User).where(User.email == email)).first()
        if user is not None:
            db.delete(user)
            db.commit()
        state = db.get(SystemSetup, SYSTEM_SETUP_ID)
        if snapshot is None:
            if state is not None:
                db.delete(state)
        else:
            if state is None:
                state = SystemSetup(**snapshot)
            else:
                for key, value in snapshot.items():
                    setattr(state, key, value)
            db.add(state)
        db.commit()
