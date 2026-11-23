"""誤判解除 API 需真 DB 的整合測試：經由 TestClient 與 superuser 權杖驗證 warnings 回傳。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.models import MiningIncidentStatus


def _stub_dismiss(
    monkeypatch: pytest.MonkeyPatch, failures: list[str]
) -> dict[str, object]:
    captured: dict[str, object] = {}

    def fake_dismiss(**kwargs: object) -> tuple:
        captured.update(kwargs)
        incident = SimpleNamespace(
            id=uuid.uuid4(),
            vmid=101,
            user_id=uuid.uuid4(),
            node="pve1",
            resource_type="qemu",
            avg_cpu=97.5,
            window_hours=6,
            snapshot_name=None,
            status=MiningIncidentStatus.dismissed,
            detected_at=datetime.now(timezone.utc),
            suspended_at=None,
            reviewed_by=None,
            reviewed_at=None,
            review_note="誤判；恢復失敗，請手動開機：PVE down",
        )
        return incident, failures

    monkeypatch.setattr(
        "app.api.routes.mining_incidents.mining_service.dismiss_incident",
        fake_dismiss,
    )
    return captured


def test_dismiss_endpoint_returns_warnings(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _stub_dismiss(monkeypatch, ["恢復失敗，請手動開機：PVE down"])
    incident_id = uuid.uuid4()

    resp = client.post(
        f"{settings.API_V1_STR}/mining-incidents/{incident_id}/dismiss",
        headers=superuser_token_headers,
        json={"exempt": False, "note": "誤判"},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["warnings"] == ["恢復失敗，請手動開機：PVE down"]
    assert data["status"] == "dismissed"
    assert captured["incident_id"] == incident_id
    assert captured["exempt"] is False
    assert captured["note"] == "誤判"


def test_dismiss_endpoint_returns_empty_warnings_on_clean_dismiss(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_dismiss(monkeypatch, [])

    resp = client.post(
        f"{settings.API_V1_STR}/mining-incidents/{uuid.uuid4()}/dismiss",
        headers=superuser_token_headers,
        json={"exempt": False, "note": "誤判"},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["warnings"] == []
    assert resp.json()["status"] == "dismissed"
