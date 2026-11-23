"""firewall_service 的封鎖網段（extra block rules）：marker 規則的更新與排序、套用失敗的記錄、子網設定讀取，以及逐台 VM 同步。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import app.infrastructure.proxmox.operations as pve_ops
from app.exceptions import ProxmoxError
from app.services.network import firewall_service as fw
from app.services.network import ip_management_service
from tests.services.firewall._fakes import FakeFirewall, _install_fw

GATEWAY_DEFAULT = "SkyLab:gateway:default"


# ─── _upsert_marker_rule ─────────────────────────────────────────────────────


def test_upsert_marker_rule_raises_when_rules_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fw(monkeypatch, FakeFirewall(fail=("get",)))
    with pytest.raises(ProxmoxError):
        fw._upsert_marker_rule("pve1", 100, "qemu", dest="10.9.0.0/16", comment="c")


def test_upsert_marker_rule_updates_dest_and_moves_above_accept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rules = [
        {"pos": 0, "type": "out", "action": "ACCEPT", "comment": GATEWAY_DEFAULT},
        {
            "pos": 1,
            "type": "out",
            "action": "DROP",
            "dest": "10.8.0.0/16",
            "comment": "c",
        },
    ]
    firewall = _install_fw(monkeypatch, FakeFirewall(rules=rules))

    result = fw._upsert_marker_rule(
        "pve1", 100, "qemu", dest="10.9.0.0/16", comment="c"
    )

    assert result == "updated"
    assert firewall.calls[0] == (
        "put",
        1,
        {
            "type": "out",
            "action": "DROP",
            "dest": "10.9.0.0/16",
            "enable": 1,
            "comment": "c",
        },
    )
    assert firewall.calls[1] == ("put", 1, {"moveto": 0})


def test_upsert_marker_rule_reorder_failure_is_logged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # pos 缺值時 int(None) 失敗，只記錄警告；dest 相同所以是 skipped
    rules = [
        {
            "pos": None,
            "type": "out",
            "action": "DROP",
            "dest": "10.9.0.0/16",
            "comment": "c",
        }
    ]
    firewall = _install_fw(monkeypatch, FakeFirewall(rules=rules))

    result = fw._upsert_marker_rule(
        "pve1", 100, "qemu", dest="10.9.0.0/16", comment="c"
    )

    assert result == "skipped"
    assert firewall.calls == []


def test_enforce_block_rule_order_swallows_api_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(node: str, vmid: int, rtype: str) -> Any:
        raise RuntimeError("no api")

    monkeypatch.setattr(fw, "_firewall_api", boom)
    assert fw.enforce_block_rule_order("pve1", 100, "qemu") == 0


# ─── _apply_extra_block_rules ────────────────────────────────────────────────


def test_apply_extra_block_rules_records_list_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fw(monkeypatch, FakeFirewall(fail=("get",)))

    stats = fw._apply_extra_block_rules("pve1", 100, "qemu", ["10.9.0.0/16"])

    assert stats["errors"] == [{"vmid": 100, "error": "list rules failed: get boom"}]


def test_apply_extra_block_rules_records_delete_and_upsert_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rules = [
        {
            "pos": 0,
            "type": "out",
            "action": "DROP",
            "comment": "SkyLab:block-extra:deadbeef",
        },
        {
            "pos": 1,
            "type": "out",
            "action": "DROP",
            "comment": "campus-cloud:block-local-subnet",
        },
    ]
    _install_fw(monkeypatch, FakeFirewall(rules=rules, fail=("delete",)))

    def failing_upsert(*args: Any, **kwargs: Any) -> str:
        raise ProxmoxError("upsert boom")

    monkeypatch.setattr(fw, "_upsert_marker_rule", failing_upsert)

    stats = fw._apply_extra_block_rules("pve1", 100, "qemu", ["10.9.0.0/16"])

    assert stats["deleted"] == []
    errors = stats["errors"]
    assert {"vmid": 100, "dest": "10.9.0.0/16", "error": "upsert boom"} in errors
    assert sum(1 for e in errors if "delete orphan" in e["error"]) == 2


# ─── _load_subnet_settings / sync_extra_block_rules ─────────────────────────


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        (None, ([], None, None)),
        (
            SimpleNamespace(gateway_vm_ip="10.0.0.254", platform_ip="10.0.0.5"),
            (["10.9.0.0/16"], "10.0.0.254", "10.0.0.5"),
        ),
    ],
)
def test_load_subnet_settings(
    monkeypatch: pytest.MonkeyPatch, config: Any, expected: tuple
) -> None:
    monkeypatch.setattr(ip_management_service, "get_subnet_config", lambda s: config)
    monkeypatch.setattr(
        ip_management_service,
        "get_extra_blocked_subnets",
        lambda c: [] if c is None else ["10.9.0.0/16"],
    )

    assert fw._load_subnet_settings() == expected


def test_sync_extra_block_rules_records_listing_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        fw, "_load_subnet_settings", lambda: (["10.9.0.0/16"], None, None)
    )

    def boom() -> list[dict]:
        raise RuntimeError("pve down")

    monkeypatch.setattr(pve_ops, "list_all_resources", boom)

    result = fw.sync_extra_block_rules()

    assert result["extra_blocks"]["targets"] == ["10.9.0.0/16"]
    assert result["extra_blocks"]["errors"] == [{"vmid": None, "error": "pve down"}]


def test_sync_extra_block_rules_aggregates_per_vm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        fw, "_load_subnet_settings", lambda: (["10.9.0.0/16"], None, "10.0.0.5")
    )
    monkeypatch.setattr(
        pve_ops,
        "list_all_resources",
        lambda: [
            {"vmid": 100, "node": "pve1", "type": "qemu"},
            {"vmid": "101", "node": "pve1", "type": "lxc"},
            {"vmid": 102, "node": None, "type": "qemu"},
            {"vmid": 103, "node": "pve2", "type": "qemu"},
        ],
    )
    seen: list[tuple] = []

    def fake_apply(node: str, vmid: int, rtype: str, targets: list[str]) -> dict:
        seen.append((node, vmid, rtype))
        if vmid == 103:
            raise RuntimeError("apply boom")
        return {"created": [f"{vmid}"], "deleted": ["old"]}

    monkeypatch.setattr(fw, "_apply_extra_block_rules", fake_apply)
    ssh_seen: list[tuple] = []

    def fake_platform(node: str, vmid: int, rtype: str, platform_ip: str | None) -> str:
        ssh_seen.append((vmid, platform_ip))
        if vmid == 101:
            raise RuntimeError("ssh boom")
        return "created"

    monkeypatch.setattr(fw, "_apply_platform_ssh_rule", fake_platform)

    full = fw.sync_extra_block_rules()
    result = full["extra_blocks"]

    assert seen == [("pve1", 100, "qemu"), ("pve1", 101, "lxc"), ("pve2", 103, "qemu")]
    assert result["created"] == ["100", "101"]
    assert result["deleted"] == ["old", "old"]
    # 封鎖網段失敗的那台仍要同步主系統 SSH 規則；SSH 規則的失敗併進同一份 errors
    assert ssh_seen == [(100, "10.0.0.5"), (101, "10.0.0.5"), (103, "10.0.0.5")]
    assert result["errors"] == [
        {"vmid": 101, "error": "platform-ssh: ssh boom"},
        {"vmid": 103, "error": "apply boom"},
    ]
    assert full["platform_ssh"]["platform_ip"] == "10.0.0.5"
    assert full["platform_ssh"]["created"] == [100, 103]
