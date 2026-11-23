"""firewall_service 的 create_connection 與 _rollback_gateway_rules：輸入驗證、Internet 到 VM 與 VM 之間的連線建立（含雙向），以及失敗時的回滾。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import app.repositories.gateway_config as gw_repo
from app.exceptions import BadRequestError, NotFoundError, ProxmoxError
from app.schemas.firewall import PortSpec
from app.services.network import firewall_service as fw
from app.services.network import nat_service, reverse_proxy_service

GATEWAY_DEFAULT = "SkyLab:gateway:default"


# ─── _rollback_gateway_rules ────────────────────────────────────────────────


def test_rollback_gateway_rules_logs_removal_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    removed: list[Any] = []
    monkeypatch.setattr(
        nat_service, "remove_nat_rules", lambda session, rules: removed.extend(rules)
    )

    def boom(session: Any, rules: list) -> None:
        raise RuntimeError("proxy removal boom")

    monkeypatch.setattr(reverse_proxy_service, "remove_reverse_proxy_rules", boom)

    fw._rollback_gateway_rules(object(), 100, ["nat1"], ["proxy1"])

    assert removed == ["nat1"]


# ─── create_connection ──────────────────────────────────────────────────────


@pytest.fixture
def conn_env(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    state = SimpleNamespace(
        resources={
            100: {"node": "pve1", "type": "qemu"},
            200: {"node": "pve2", "type": "lxc"},
        },
        ips={100: "10.0.0.100", 200: "10.0.0.200"},
        rules={100: [], 200: []},
        created=[],
        deleted=[],
        enforced=[],
        asserted=[],
        fail_create_on=None,
    )

    def find_resource(vmid: int) -> dict:
        if vmid not in state.resources:
            raise NotFoundError("missing")
        return state.resources[vmid]

    monkeypatch.setattr(
        fw, "proxmox_service", SimpleNamespace(find_resource=find_resource)
    )

    def fake_create_rule(node: str, vmid: int, rtype: str, rule: dict) -> None:
        if state.fail_create_on is not None and state.fail_create_on(rule):
            raise ProxmoxError("create boom")
        state.created.append((vmid, rule))
        state.rules.setdefault(vmid, []).append(
            {**rule, "pos": len(state.rules.get(vmid, []))}
        )

    monkeypatch.setattr(fw, "create_rule", fake_create_rule)
    monkeypatch.setattr(
        fw,
        "get_vm_firewall_rules",
        lambda node, vmid, rtype: list(state.rules.get(vmid, [])),
    )
    monkeypatch.setattr(
        fw,
        "delete_rule_by_pos",
        lambda node, vmid, rtype, pos: state.deleted.append((vmid, pos)),
    )
    monkeypatch.setattr(
        fw,
        "enforce_block_rule_order",
        lambda node, vmid, rtype: state.enforced.append(vmid) or 0,
    )
    monkeypatch.setattr(
        fw, "_get_publishable_vm_ip", lambda vmid, session=None: state.ips.get(vmid)
    )
    monkeypatch.setattr(
        fw,
        "assert_publishable_vm_ip",
        lambda session, ip, *, vmid: state.asserted.append((vmid, ip)),
    )
    return state


def test_create_connection_input_validation(conn_env: SimpleNamespace) -> None:
    port = [PortSpec(port=80, protocol="tcp")]
    with pytest.raises(BadRequestError):
        fw.create_connection(100, 200, [])
    with pytest.raises(BadRequestError):
        fw.create_connection(100, 100, port)
    with pytest.raises(BadRequestError):
        fw.create_connection(None, None, port)
    with pytest.raises(BadRequestError):
        fw.create_connection(None, 999, port)
    with pytest.raises(BadRequestError):
        fw.create_connection(999, 200, port)


def test_create_connection_inbound_requires_session_for_gateway(
    conn_env: SimpleNamespace,
) -> None:
    with pytest.raises(BadRequestError):
        fw.create_connection(
            None, 100, [PortSpec(port=80, protocol="tcp", external_port=8080)]
        )


def test_create_connection_inbound_requires_gateway_config(
    conn_env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(gw_repo, "get_gateway_config", lambda session: None)
    with pytest.raises(BadRequestError):
        fw.create_connection(
            None,
            100,
            [PortSpec(port=80, protocol="tcp", domain="a.example.com")],
            session=object(),
        )


def test_create_connection_inbound_requires_target_ip(
    conn_env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        gw_repo,
        "get_gateway_config",
        lambda session: SimpleNamespace(host="gw", encrypted_private_key="k"),
    )
    conn_env.ips[100] = None
    with pytest.raises(BadRequestError):
        fw.create_connection(
            None,
            100,
            [PortSpec(port=80, protocol="tcp", external_port=8080)],
            session=object(),
        )
    assert conn_env.created == []


def test_create_connection_inbound_rollback_tolerates_delete_errors(
    conn_env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn_env.fail_create_on = lambda rule: rule.get("dport") == "22"

    def failing_delete(node: str, vmid: int, rtype: str, pos: int) -> None:
        raise ProxmoxError("delete boom")

    monkeypatch.setattr(fw, "delete_rule_by_pos", failing_delete)

    with pytest.raises(ProxmoxError, match="create boom"):
        fw.create_connection(
            None,
            100,
            [PortSpec(port=80, protocol="tcp"), PortSpec(port=22, protocol="tcp")],
        )


def test_create_connection_inbound_rollback_tolerates_listing_errors(
    conn_env: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn_env.fail_create_on = lambda rule: rule.get("dport") == "22"

    def failing_list(node: str, vmid: int, rtype: str) -> list[dict]:
        raise ProxmoxError("list boom")

    monkeypatch.setattr(fw, "get_vm_firewall_rules", failing_list)

    with pytest.raises(ProxmoxError, match="create boom"):
        fw.create_connection(
            None,
            100,
            [PortSpec(port=80, protocol="tcp"), PortSpec(port=22, protocol="tcp")],
        )


def test_create_connection_to_gateway_restores_default_marker(
    conn_env: SimpleNamespace,
) -> None:
    fw.create_connection(
        100,
        None,
        [PortSpec(port=443, protocol="tcp"), PortSpec(port=0, protocol="icmp")],
    )

    comments = [rule["comment"] for _vmid, rule in conn_env.created]
    assert comments == [
        GATEWAY_DEFAULT,
        "SkyLab:100->gateway:443/tcp",
        "SkyLab:100->gateway:icmp",
    ]
    assert conn_env.enforced == [100]


def test_create_connection_vm_to_vm_requires_ips(conn_env: SimpleNamespace) -> None:
    port = [PortSpec(port=22, protocol="tcp")]
    conn_env.ips[100] = None
    with pytest.raises(BadRequestError):
        fw.create_connection(100, 200, port)

    conn_env.ips[100] = "10.0.0.100"
    with pytest.raises(BadRequestError):
        fw.create_connection(100, 999, port)

    conn_env.ips[200] = None
    with pytest.raises(BadRequestError):
        fw.create_connection(100, 200, port)
    assert conn_env.created == []


def test_create_connection_vm_to_vm_one_way_validates_ips(
    conn_env: SimpleNamespace,
) -> None:
    conn_env.rules[100] = [
        {"pos": 0, "type": "out", "action": "ACCEPT", "comment": GATEWAY_DEFAULT}
    ]

    fw.create_connection(
        100, 200, [PortSpec(port=22, protocol="tcp")], session=object()
    )

    assert conn_env.asserted == [(100, "10.0.0.100"), (200, "10.0.0.200")]
    assert [(vmid, rule["type"]) for vmid, rule in conn_env.created] == [
        (200, "in"),
        (100, "out"),
    ]
    out_rule = conn_env.created[1][1]
    assert out_rule["pos"] == 0
    assert out_rule["dest"] == "10.0.0.200"


def test_create_connection_vm_to_vm_bidirectional(conn_env: SimpleNamespace) -> None:
    fw.create_connection(
        100,
        200,
        [PortSpec(port=0, protocol="icmp")],
        direction="bidirectional",
    )

    assert conn_env.asserted == []
    assert [
        (vmid, rule["type"], rule["comment"]) for vmid, rule in conn_env.created
    ] == [
        (200, "in", "SkyLab:100->200:icmp"),
        (100, "out", "SkyLab:100->200:icmp"),
        (100, "in", "SkyLab:200->100:icmp"),
        (200, "out", "SkyLab:200->100:icmp"),
    ]
    assert conn_env.created[2][1]["source"] == "10.0.0.200"
    assert conn_env.created[3][1]["dest"] == "10.0.0.100"
