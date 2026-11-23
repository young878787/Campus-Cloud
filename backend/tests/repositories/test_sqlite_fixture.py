"""共用 sqlite fixture 的隔離與建表完整性。"""

from sqlalchemy import Engine, inspect
from sqlmodel import Session, SQLModel, select

from app.models import User


def _add_shared_email_user(session: Session) -> None:
    session.add(User(email="shared@example.com", hashed_password="x"))
    session.commit()


def test_isolation_first(sqlite_session: Session) -> None:
    _add_shared_email_user(sqlite_session)
    assert len(sqlite_session.exec(select(User)).all()) == 1


def test_isolation_second(sqlite_session: Session) -> None:
    _add_shared_email_user(sqlite_session)
    assert len(sqlite_session.exec(select(User)).all()) == 1


def test_engine_has_all_metadata_tables(sqlite_engine: Engine) -> None:
    assert len(inspect(sqlite_engine).get_table_names()) == len(
        SQLModel.metadata.tables
    )


def test_session_writes_visible_to_new_session(
    sqlite_session: Session, sqlite_engine: Engine
) -> None:
    _add_shared_email_user(sqlite_session)
    with Session(sqlite_engine) as other:
        assert other.exec(select(User)).one().email == "shared@example.com"
