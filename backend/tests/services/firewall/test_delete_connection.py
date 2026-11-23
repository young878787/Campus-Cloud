"""firewall_service 的 delete_connection 與 _delete_matching_rules：依來源與目標 VM、port 刪除對應規則，部分失敗時仍盡力清除其餘項目。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.exceptions import NotFoundError, ProxmoxError
from app.schemas.firewall import PortSpec
from app.services.network import firewall_service as fw
from app.services.network import nat_service, reverse_proxy_service

GATEWAY_DEFAULT = "SkyLab:gateway:default"


# ─── delete_connection ──────────────────────────────────────────────────────


@pytest.fixture
def del_env(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    state = SimpleNamespace(
        resources={
            100: {"node": "pve1", "type": "qemu"},
            200: {"node": "pve2", "type": "lxc"},
        },
        calls=[],
        fail_calls=set(),
        gateway=[],
    )

    def find_resource(vmid: int) -> dict:
        if vmid not in state.resources:
            raise NotFoundError("missing")
        return state.resources[vmid]

    monkeypatch.setattr(
        fw, "proxmox_service", SimpleNamespace(find_resource=find_resource)
    )

    def fake_delete_matching(**kwargs: Any) -> None:
        state.calls.append(kwargs)
        if len(state.calls) in state.fail_calls:
            raise RuntimeError("delete matching boom")

    monkeypatch.setattr(fw, "_delete_matching_rules", fake_delete_matching)
    monkeypatch.setattr(
        nat_service,
        "remove_nat_rules_for_vmid",
        lambda session, vmid: state.gateway.append(("nat_all", vmid)),
    )
    monkeypatch.setattr(
        reverse_proxy_service,
        "remove_reverse_proxy_rules_for_vmid",
        lambda session, vmid: state.gateway.append(("proxy_all", vmid)),
    )
    monkeypatch.setattr(
        nat_service,
        "remove_nat_rules_by_internal_port",
        lambda session, vmid, port, proto: state.gateway.append(
            ("nat", vmid, port, proto)
        ),
    )
    monkeypatch.setattr(
        reverse_proxy_service,
        "remove_reverse_proxy_rules_by_internal_port",
        lambda session, vmid, port: state.gateway.append(("proxy", vmid, port)),
    )
    return state


def test_delete_connection_inbound_noops(del_env: SimpleNamespace) -> None:
    fw.delete_connection(None, None)
    fw.delete_connection(None, 999)
    assert del_env.calls == []


def test_delete_connection_inbound_clears_all_gateway_rules(
    del_env: SimpleNamespace,
) -> None:
    fw.delete_connection(None, 100, session=object())
    assert del_env.gateway == [("nat_all", 100), ("proxy_all", 100)]


def test_delete_connection_to_gateway(del_env: SimpleNamespace) -> None:
    fw.delete_connection(999, None)
    assert del_env.calls == []

    fw.delete_connection(100, None)
    assert del_env.calls == [
        {
            "node": "pve1",
            "vmid": 100,
            "resource_type": "qemu",
            "source_vmid": 100,
            "target_vmid": None,
            "ports": None,
        }
    ]


def test_delete_connection_vm_to_vm_missing_resources(del_env: SimpleNamespace) -> None:
    fw.delete_connection(100, 999)
    fw.delete_connection(999, 200)
    assert del_env.calls == []


def test_delete_connection_vm_to_vm_best_effort_failures(
    del_env: SimpleNamespace,
) -> None:
    del_env.fail_calls = {2, 3, 4}

    fw.delete_connection(100, 200)

    assert len(del_env.calls) == 4


# ─── _delete_matching_rules ─────────────────────────────────────────────────


@pytest.fixture
def match_env(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    state = SimpleNamespace(rules=[], deleted=[], fail_delete=False)
    monkeypatch.setattr(
        fw, "get_vm_firewall_rules", lambda node, vmid, rtype: state.rules
    )

    def fake_delete(node: str, vmid: int, rtype: str, pos: int) -> None:
        if state.fail_delete:
            raise ProxmoxError("delete boom")
        state.deleted.append(pos)

    monkeypatch.setattr(fw, "delete_rule_by_pos", fake_delete)
    return state


def _delete(
    source: int | None, target: int | None, ports: list[PortSpec] | None
) -> None:
    fw._delete_matching_rules(
        node="pve1",
        vmid=100,
        resource_type="qemu",
        source_vmid=source,
        target_vmid=target,
        ports=ports,
    )


def test_delete_matching_internet_rules(match_env: SimpleNamespace) -> None:
    match_env.rules = [
        {"pos": 0, "comment": "SkyLab:gateway->100:80/tcp"},
        {"pos": 1, "comment": "SkyLab:gateway->100:22/tcp"},
        {"pos": 2, "comment": "SkyLab:gateway->101:80/tcp"},
        {"pos": 3, "comment": "manual rule"},
        {"pos": 4, "comment": None},
        {"pos": 5},
    ]

    _delete(None, 100, [PortSpec(port=80, protocol="tcp")])

    assert match_env.deleted == [0]


def test_delete_matching_gateway_rules_without_port_filter(
    match_env: SimpleNamespace,
) -> None:
    match_env.rules = [
        {"pos": 0, "comment": GATEWAY_DEFAULT},
        {"pos": 1, "comment": "SkyLab:100->gateway:443/tcp"},
        {"pos": 2, "comment": "SkyLab:101->gateway:443/tcp"},
        {"pos": 3, "comment": "SkyLab:gateway->100:80/tcp"},
    ]

    _delete(100, None, None)

    assert match_env.deleted == [1, 0]


def test_delete_matching_vm_to_vm_rules_and_failures(
    match_env: SimpleNamespace,
) -> None:
    match_env.rules = [
        {"pos": 0, "comment": "SkyLab:100->200:22/tcp"},
        {"pos": 1, "comment": "SkyLab:200->100:22/tcp"},
        {"pos": 2, "comment": "SkyLab:100->200:icmp"},
    ]

    _delete(100, 200, None)
    assert match_env.deleted == [2, 0]

    match_env.deleted.clear()
    match_env.fail_delete = True
    _delete(100, 200, [PortSpec(port=22, protocol="tcp")])
    assert match_env.deleted == []
