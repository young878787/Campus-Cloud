"""資源告警帶 PVE 連線的整合測試（需真 Postgres）：API 回傳連線名稱，migration 只回填開啟中的告警。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.alembic.versions import alertconn01_alert_connection as migration
from app.core.config import settings
from app.core.db import engine as pg_engine
from app.models import (
    AlertEvent,
    AlertMetric,
    AlertScope,
    ProxmoxConnection,
    ProxmoxNode,
    Resource,
    User,
)
from app.services.monitoring import alert_service

NOW = datetime(2026, 10, 12, 8, 0, tzinfo=UTC)


def test_alerts_api_returns_connection_name(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = SimpleNamespace(
        id=uuid.uuid4(), scope=AlertScope.vm, connection_id=7, target="100",
        metric=AlertMetric.memory, value=93.0, threshold=90.0, message="m",
        created_at=NOW, resolved_at=None, acknowledged_by=None, acknowledged_at=None,
    )
    monkeypatch.setattr(
        alert_service.governance_repo, "list_alerts", lambda **_: [row]
    )
    monkeypatch.setattr(alert_service, "_connection_names", lambda s: {7: "lab-cluster"})
    r = client.get(
        f"{settings.API_V1_STR}/monitoring/alerts?active=true",
        headers=superuser_token_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body[0]["connection_id"] == 7
    assert body[0]["connection_name"] == "lab-cluster"


# ─── migration：只回填開啟中的告警 ─────────────────────────────────────


def test_migration_backfills_open_alerts_only(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 直接在真的 PostgreSQL 上跑 migration（交易最後 rollback）：明確宣告 guarded
    # db fixture，DB guard 才不會把它當成純單元測試擋掉
    suffix = uuid.uuid4().hex[:8]
    vmid = 900_000 + int(suffix[:4], 16)
    with pg_engine.connect() as connection:
        transaction = connection.begin()
        try:
            session = Session(bind=connection)
            owner = session.exec(select(User)).first()
            assert owner is not None
            conn = ProxmoxConnection(
                name=f"alertconn-{suffix}", host="10.9.9.9", user="root@pam",
                encrypted_password="x",
            )
            session.add(conn)
            session.flush()
            session.add(
                ProxmoxNode(name=f"n-{suffix}", host="10.9.9.10", connection_id=conn.id)
            )
            session.add(
                Resource(
                    vmid=vmid, user_id=owner.id, environment_type="vm",
                    connection_id=conn.id, created_at=NOW,
                )
            )

            def _alert(scope: AlertScope, target: str, *, resolved: bool) -> AlertEvent:
                event = AlertEvent(
                    scope=scope, target=target, metric=AlertMetric.cpu, value=95.0,
                    threshold=90.0, message="m", created_at=NOW,
                    resolved_at=NOW + timedelta(minutes=5) if resolved else None,
                )
                session.add(event)
                return event

            node_open = _alert(AlertScope.node, f"n-{suffix}", resolved=False)
            vm_open = _alert(AlertScope.vm, str(vmid), resolved=False)
            vm_resolved = _alert(AlertScope.vm, str(vmid), resolved=True)
            unknown = _alert(AlertScope.vm, str(vmid + 1), resolved=False)
            session.flush()

            monkeypatch.setattr(
                migration, "op", Operations(MigrationContext.configure(connection))
            )
            migration.upgrade()

            def _conn(event: AlertEvent) -> int | None:
                return connection.execute(
                    sa.text("SELECT connection_id FROM alert_events WHERE id = :id"),
                    {"id": event.id},
                ).scalar_one()

            assert _conn(node_open) == conn.id
            assert _conn(vm_open) == conn.id
            assert _conn(vm_resolved) is None
            assert _conn(unknown) is None
            session.close()
        finally:
            transaction.rollback()
