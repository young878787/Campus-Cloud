"""每個測試各自拿到全新、隔離、含所有表的記憶體 SQLite：從每個 worker 的範本 DB 複製，不再逐測試 create_all。"""

from collections.abc import Generator

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel


def _memory_engine() -> Engine:
    return create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


@pytest.fixture(scope="session")
def _sqlite_template() -> Generator[tuple[Engine, frozenset[str]], None, None]:
    """建立範本 DB 一次，並記下建表當下的表名，供逐測試複製前比對。"""
    engine = _memory_engine()
    SQLModel.metadata.create_all(engine)
    yield engine, frozenset(SQLModel.metadata.tables)
    engine.dispose()


@pytest.fixture()
def sqlite_engine(
    _sqlite_template: tuple[Engine, frozenset[str]],
) -> Generator[Engine, None, None]:
    template, built_tables = _sqlite_template
    engine = _memory_engine()
    if frozenset(SQLModel.metadata.tables) == built_tables:
        with template.connect() as src, engine.connect() as dst:
            src.connection.driver_connection.backup(dst.connection.driver_connection)
    else:
        # 範本建好後 metadata 又多了表：範本已不完整，改為現場建表
        SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def sqlite_session(sqlite_engine: Engine) -> Generator[Session, None, None]:
    with Session(sqlite_engine) as session:
        yield session
