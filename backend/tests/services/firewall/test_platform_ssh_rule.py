"""firewall_service 的主系統 SSH 規則（_apply_platform_ssh_rule／ensure_platform_ssh_rule）：建立並置頂、更新來源、清除 IP 時刪除，以及失敗時的記錄。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.services.network import firewall_service as fw
from app.services.network import ip_management_service
from tests.services.firewall._fakes import FakeFirewall, _install_fw

GATEWAY_DEFAULT = "SkyLab:gateway:default"
PLATFORM_SSH = "SkyLab:platform:ssh"


# ─── 主系統 SSH 規則 ─────────────────────────────────────────────────────────


def _ssh_rule(pos: int, source: str = "10.0.0.5", **extra: Any) -> dict:
    return {
        "pos": pos,
        "type": "in",
        "action": "ACCEPT",
        "source": source,
        "proto": "tcp",
        "dport": "22",
        "enable": 1,
        "comment": PLATFORM_SSH,
        **extra,
    }


def test_apply_platform_ssh_rule_creates_at_top(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    firewall = _install_fw(
        monkeypatch, FakeFirewall(rules=[{"pos": 0, "comment": GATEWAY_DEFAULT}])
    )

    assert fw._apply_platform_ssh_rule("pve1", 100, "qemu", "10.0.0.5") == "created"
    assert firewall.calls == [
        ("post", {**{k: v for k, v in _ssh_rule(0).items() if k != "pos"}, "pos": 0})
    ]


def test_apply_platform_ssh_rule_updates_source_and_moves_to_top(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    firewall = _install_fw(
        monkeypatch,
        FakeFirewall(rules=[{"pos": 0, "type": "in", "action": "DROP"}, _ssh_rule(1)]),
    )

    assert fw._apply_platform_ssh_rule("pve1", 100, "lxc", "10.0.0.9") == "updated"
    desired = {k: v for k, v in _ssh_rule(0, source="10.0.0.9").items() if k != "pos"}
    assert firewall.calls == [("put", 1, desired), ("put", 1, {"moveto": 0})]


def test_apply_platform_ssh_rule_removes_when_ip_cleared(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    firewall = _install_fw(
        monkeypatch, FakeFirewall(rules=[_ssh_rule(0), {"pos": 1}, _ssh_rule(2)])
    )

    assert fw._apply_platform_ssh_rule("pve1", 100, "qemu", None) == "deleted"
    assert firewall.calls == [("delete", 2), ("delete", 0)]


def test_ensure_platform_ssh_rule_applies_configured_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    applied: list[tuple] = []
    monkeypatch.setattr(
        ip_management_service,
        "get_subnet_config",
        lambda s: SimpleNamespace(platform_ip="10.0.0.5"),
    )
    monkeypatch.setattr(
        fw, "_apply_platform_ssh_rule", lambda *args: applied.append(args) or "created"
    )

    fw.ensure_platform_ssh_rule(object(), "pve1", 100, "qemu")

    assert applied == [("pve1", 100, "qemu", "10.0.0.5")]


@pytest.mark.parametrize("config", [None, SimpleNamespace(platform_ip=None)])
def test_ensure_platform_ssh_rule_noop_without_platform_ip(
    monkeypatch: pytest.MonkeyPatch, config: Any
) -> None:
    monkeypatch.setattr(ip_management_service, "get_subnet_config", lambda s: config)
    monkeypatch.setattr(fw, "_firewall_api", lambda *a: pytest.fail("不該碰 PVE"))

    fw.ensure_platform_ssh_rule(object(), "pve1", 100, "qemu")


def test_ensure_platform_ssh_rule_logs_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def boom(s: Any) -> Any:
        raise RuntimeError("db down")

    monkeypatch.setattr(ip_management_service, "get_subnet_config", boom)

    fw.ensure_platform_ssh_rule(object(), "pve1", 100, "qemu")

    assert any(
        r.levelname == "ERROR" and "db down" in r.getMessage() for r in caplog.records
    )
