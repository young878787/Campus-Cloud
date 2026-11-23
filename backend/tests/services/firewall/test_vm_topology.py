"""firewall_service 的迷你拓撲（_topology_node_for_vm／get_vm_topology）：節點 IP 與防火牆狀態、可管理權限的判定，以及對端節點的位置與未知機器的過濾。"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.exceptions import NotFoundError
from app.schemas.firewall import TopologyEdge
from app.services.network import firewall_service as fw

# ─── 迷你拓撲 ───────────────────────────────────────────────────────────────


def test_topology_node_for_vm_with_details_degrades_on_options_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fw, "_get_vm_ip", lambda vmid, session=None: "10.0.0.5")

    def boom(node: str, vmid: int, rtype: str) -> dict:
        raise RuntimeError("options boom")

    monkeypatch.setattr(fw, "get_firewall_options", boom)

    node = fw._topology_node_for_vm(
        100,
        {"node": "pve1", "type": "lxc", "name": "web", "status": "running"},
        None,
        x=1.0,
        y=2.0,
        with_details=True,
    )

    assert node.ip_address == "10.0.0.5"
    assert node.firewall_enabled is False
    assert node.vm_type == "lxc"


def test_get_vm_topology_marks_who_can_manage_each_machine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """連線要寫兩端的規則：別人的機器、快速練習機、平台外建的機器都標成不能管。"""
    owner = SimpleNamespace(id=uuid.uuid4(), role="student", is_superuser=False)
    monkeypatch.setattr(
        fw,
        "proxmox_service",
        SimpleNamespace(
            find_resource=lambda vmid: {
                "node": "pve1", "type": "qemu", "name": f"vm{vmid}", "status": "running",
            }
        ),
    )
    monkeypatch.setattr(
        fw,
        "get_connections_from_rules",
        lambda vmids: [
            TopologyEdge(source_vmid=100, target_vmid=vmid, ports=[])
            for vmid in (200, 300, 400)
        ],
    )
    monkeypatch.setattr(fw, "_enrich_edges_from_db", lambda edges, session: None)
    monkeypatch.setattr(fw, "_get_vm_ip", lambda vmid, session=None: None)
    monkeypatch.setattr(fw, "get_firewall_options", lambda node, vmid, rtype: {})
    rows = {
        100: SimpleNamespace(vmid=100, user_id=owner.id, teaching_class_id=None, allocation_scope="personal"),
        200: SimpleNamespace(vmid=200, user_id=uuid.uuid4(), teaching_class_id=None, allocation_scope="personal"),
        300: SimpleNamespace(vmid=300, user_id=owner.id, teaching_class_id=None, allocation_scope="personal"),
        # 400 沒有 Resource 列（平台外建的機器）
    }
    monkeypatch.setattr(
        fw.resource_repo,
        "get_resources_by_vmids",
        lambda *, session, vmids: {v: rows[v] for v in vmids if v in rows},
    )
    monkeypatch.setattr(
        fw.resource_access, "list_owned_teaching_class_ids", lambda *, session, user: set()
    )
    monkeypatch.setattr(
        fw.resource_kind,
        "classify_many",
        lambda session, resources: {100: "personal", 200: "personal", 300: "quick_practice"},
    )
    monkeypatch.setattr(fw, "can_bypass_resource_ownership", lambda user: False)

    resp = fw.get_vm_topology(100, object(), user=owner)  # type: ignore[arg-type]

    assert {n.vmid: n.can_manage for n in resp.nodes if n.vmid is not None} == {
        100: True,   # 自己的個人機
        200: False,  # 別人的機器
        300: False,  # 自己的快速練習機
        400: False,  # 沒有 Resource 列，只有管理員能動
    }

    monkeypatch.setattr(fw, "can_bypass_resource_ownership", lambda user: True)
    admin_view = fw.get_vm_topology(100, object(), user=owner)  # type: ignore[arg-type]
    assert {n.vmid: n.can_manage for n in admin_view.nodes if n.vmid is not None}[400] is True


def test_get_vm_topology_places_peers_and_filters_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def find_resource(vmid: int) -> dict:
        if vmid == 300:
            raise NotFoundError("missing")
        return {
            "node": "pve1",
            "type": "qemu",
            "name": f"vm{vmid}",
            "status": "running",
        }

    monkeypatch.setattr(
        fw, "proxmox_service", SimpleNamespace(find_resource=find_resource)
    )
    monkeypatch.setattr(
        fw,
        "get_connections_from_rules",
        lambda vmids: [
            TopologyEdge(source_vmid=100, target_vmid=200, ports=[]),
            TopologyEdge(source_vmid=300, target_vmid=100, ports=[]),
            TopologyEdge(source_vmid=None, target_vmid=100, ports=[]),
            TopologyEdge(source_vmid=100, target_vmid=None, ports=[]),
        ],
    )
    monkeypatch.setattr(fw, "_enrich_edges_from_db", lambda edges, session: None)
    monkeypatch.setattr(fw, "_get_vm_ip", lambda vmid, session=None: "10.0.0.100")
    monkeypatch.setattr(
        fw, "get_firewall_options", lambda node, vmid, rtype: {"enable": 1}
    )

    resp = fw.get_vm_topology(100, object())  # type: ignore[arg-type]

    assert [n.vmid for n in resp.nodes] == [200, 100, None]
    peer, center, internet = resp.nodes
    assert (peer.position_x, peer.position_y, peer.ip_address) == (0.0, 40.0, None)
    assert center.position_x == 340.0
    assert center.position_y == 40.0 + 110.0 / 2
    assert center.firewall_enabled is True
    assert internet.position_x == 680.0
    assert [(e.source_vmid, e.target_vmid) for e in resp.edges] == [
        (100, 200),
        (None, 100),
        (100, None),
    ]
