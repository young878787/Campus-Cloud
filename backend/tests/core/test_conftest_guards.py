from types import SimpleNamespace

import pytest


def test_unit_test_db_guard_blocks_application_engine():
    from app.core.db import engine

    with pytest.raises(RuntimeError, match="isolated engine"):
        engine.connect()


def test_seed_guard_skips_units_and_rejects_non_test_target(monkeypatch):
    from app.core.config import settings
    from tests import conftest

    touched = []
    monkeypatch.setattr(conftest, "Session", lambda *_: touched.append(True))
    seed = conftest._seed_first_superuser.__wrapped__
    seed(
        SimpleNamespace(
            session=SimpleNamespace(items=[SimpleNamespace(fixturenames=[])])
        )
    )
    monkeypatch.delenv("PYTEST_ALLOW_NON_TEST_DB", raising=False)
    monkeypatch.setattr(settings, "POSTGRES_SERVER", "example.invalid")
    monkeypatch.setattr(settings, "POSTGRES_DB", "app")

    def item_for(function):
        return SimpleNamespace(
            _fixtureinfo=SimpleNamespace(
                name2fixturedefs={"db": [SimpleNamespace(func=function)]}
            )
        )

    local_db_item = item_for(lambda: None)
    assert not conftest._uses_application_db(local_db_item)
    seed(SimpleNamespace(session=SimpleNamespace(items=[local_db_item])))
    canonical_db_item = item_for(conftest.db.__wrapped__)
    assert conftest._uses_application_db(canonical_db_item)
    with pytest.raises(RuntimeError, match="non-test database"):
        seed(SimpleNamespace(session=SimpleNamespace(items=[canonical_db_item])))
    assert not touched
