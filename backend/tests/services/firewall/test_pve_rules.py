"""firewall_service 的 PVE 防火牆規則讀寫：_firewall_api 依資源類型路由，低階包裝的失敗路徑，以及 firewall 啟用時的容錯。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.exceptions import ProxmoxError
from app.services.network import firewall_service as fw
from tests.services.firewall._fakes import FakeFirewall, _install_fw

# ─── _firewall_api ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("rtype", ["qemu", "lxc"])
def test_firewall_api_routes_by_resource_type(
    monkeypatch: pytest.MonkeyPatch, rtype: str
) -> None:
    api = MagicMock()
    monkeypatch.setattr(fw, "get_proxmox_api_for_node", lambda node: api)

    result = fw._firewall_api("pve1", 100, rtype)  # type: ignore[arg-type]

    node_api = api.nodes.return_value
    expected = getattr(node_api, rtype).return_value.firewall
    assert result is expected
    api.nodes.assert_called_with("pve1")
    getattr(node_api, rtype).assert_called_with(100)


# ─── 低階 PVE 包裝 ──────────────────────────────────────────────────────────


def test_get_vm_firewall_rules_none_becomes_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fw(monkeypatch, FakeFirewall(rules=None))
    assert fw.get_vm_firewall_rules("pve1", 100, "qemu") == []


def test_rule_wrappers_failure_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fw(
        monkeypatch,
        FakeFirewall(fail=("post", "put", "delete", "options_get", "options_put")),
    )

    with pytest.raises(ProxmoxError):
        fw.create_rule("pve1", 100, "qemu", {"type": "in"})
    with pytest.raises(ProxmoxError):
        fw.update_rule("pve1", 100, "qemu", 1, {})
    with pytest.raises(ProxmoxError):
        fw.delete_rule_by_pos("pve1", 100, "qemu", 1)
    assert fw.get_firewall_options("pve1", 100, "qemu") == {}
    with pytest.raises(ProxmoxError):
        fw._set_firewall_options("pve1", 100, "qemu", enable=1)


# ─── ensure_firewall_enabled ────────────────────────────────────────────────


def test_ensure_firewall_enabled_logs_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fw(monkeypatch, FakeFirewall(options={}, fail=("options_put",)))
    # 不拋出，只記錄 ERROR
    fw.ensure_firewall_enabled("pve1", 100, "qemu")
