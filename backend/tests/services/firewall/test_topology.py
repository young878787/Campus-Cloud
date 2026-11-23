"""firewall_service 的連線解析與拓撲聚合：由防火牆規則推導 edge、補上 DB 資料、描述資源來源，以及 get_topology 套用已存的版面位置。"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from app.exceptions import NotFoundError
from app.schemas.firewall import TopologyEdge
from app.services.network import firewall_service as fw

GATEWAY_DEFAULT = "SkyLab:gateway:default"


# ─── 連線解析與拓撲聚合 ─────────────────────────────────────────────────────


def test_get_connections_from_rules_skips_unreadable_vm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def find_resource(vmid: int) -> dict:
        if vmid == 999:
            raise NotFoundError("missing")
        return {"node": "pve1", "type": "qemu"}

    monkeypatch.setattr(
        fw, "proxmox_service", SimpleNamespace(find_resource=find_resource)
    )
    monkeypatch.setattr(
        fw,
        "get_vm_firewall_rules",
        lambda node, vmid, rtype: [{"pos": 0, "comment": "SkyLab:gateway->100:80/tcp"}],
    )

    edges = fw.get_connections_from_rules([100, 999])

    assert [(e.source_vmid, e.target_vmid) for e in edges] == [(None, 100)]


def test_edges_from_rules_handles_every_rule_kind() -> None:
    rules_by_vmid = {
        100: [
            {"comment": GATEWAY_DEFAULT},
            {"comment": GATEWAY_DEFAULT},
            {"comment": "SkyLab:100->gateway:443/tcp"},
            {"comment": "SkyLab:100->gateway:443/tcp"},
            {"comment": "SkyLab:100->gateway:icmp"},
            {"comment": "SkyLab:gateway->100:80/tcp"},
            {"comment": "SkyLab:100->200:22/tcp"},
            {"comment": "SkyLab:class-net:c1:100>200:tcp/8080"},
            {"comment": "not managed"},
            {"comment": None},
        ],
        101: [{"comment": "SkyLab:101->gateway:53/udp"}],
        200: [{"comment": GATEWAY_DEFAULT}],
    }

    edges = {
        (e.source_vmid, e.target_vmid): e for e in fw._edges_from_rules(rules_by_vmid)
    }

    assert set(edges) == {
        (100, None),
        (None, 100),
        (100, 200),
        (101, None),
        (200, None),
    }
    assert [(p.port, p.protocol) for p in edges[(100, None)].ports] == [
        (443, "tcp"),
        (0, "icmp"),
    ]
    assert [(p.port, p.protocol) for p in edges[(101, None)].ports] == [(53, "udp")]
    assert edges[(200, None)].ports == []
    assert edges[(100, 200)].topology_managed is True
    assert [(p.port, p.protocol) for p in edges[(100, 200)].ports] == [
        (22, "tcp"),
        (8080, "tcp"),
    ]


def test_enrich_edges_from_db_noop_without_inbound_edges() -> None:
    edges = [TopologyEdge(source_vmid=100, target_vmid=None, ports=[])]
    # 沒有 Internet→VM edge 時不碰 DB（session 傳 None 也不會出錯）
    fw._enrich_edges_from_db(edges, None)  # type: ignore[arg-type]


class _FakeResult:
    def __init__(self, rows: list[tuple]) -> None:
        self.rows = rows

    def all(self) -> list[tuple]:
        return self.rows


class _FakeSession:
    def __init__(self, *results: list[tuple]) -> None:
        self.results = list(results)
        self.statements: list[Any] = []

    def exec(self, stmt: Any) -> _FakeResult:
        self.statements.append(stmt)
        return _FakeResult(self.results.pop(0))


def test_describe_resource_origins_queries_classes_and_owners() -> None:
    class_id = uuid.uuid4()
    viewer = uuid.uuid4()
    owner_a = uuid.uuid4()
    owner_b = uuid.uuid4()
    session = _FakeSession(
        [(class_id, "Networking 101")],
        [(owner_a, "Alice", "alice@example.com"), (owner_b, None, "bob@example.com")],
    )
    resources = [
        SimpleNamespace(teaching_class_id=class_id, user_id=owner_a),
        SimpleNamespace(teaching_class_id=None, user_id=owner_b),
        SimpleNamespace(teaching_class_id=None, user_id=viewer),
    ]

    class_names, owner_names = fw._describe_resource_origins(
        session=session,  # type: ignore[arg-type]
        resources=resources,
        viewer_id=viewer,
    )

    assert class_names == {class_id: "Networking 101"}
    assert owner_names == {owner_a: "Alice", owner_b: "bob@example.com"}
    assert len(session.statements) == 2


def test_probe_topology_vm_degrades_on_options_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(node: str, vmid: int, rtype: str) -> dict:
        raise RuntimeError("options boom")

    monkeypatch.setattr(fw, "get_firewall_options", boom)
    monkeypatch.setattr(
        fw, "get_vm_firewall_rules", lambda node, vmid, rtype: [{"pos": 0}]
    )

    assert fw._probe_topology_vm({"vmid": "100", "node": "pve1", "type": "qemu"}) == (
        False,
        [{"pos": 0}],
    )


def test_probe_topology_vms_empty() -> None:
    assert fw._probe_topology_vms([]) == {}


def test_get_topology_uses_saved_layout(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_owned_classes(*, session: Any, user: Any) -> set[Any]:
        return set()

    monkeypatch.setattr(
        fw.resource_access,
        "list_reachable_resources",
        lambda *, session, user: [
            SimpleNamespace(vmid=100, user_id="u1", teaching_class_id=None),
            SimpleNamespace(vmid=101, user_id="u1", teaching_class_id=None),
            # PVE 上找不到的機器不出現在拓撲
            SimpleNamespace(vmid=102, user_id="u1", teaching_class_id=None),
        ],
    )
    monkeypatch.setattr(
        fw.resource_access,
        "list_owned_teaching_class_ids",
        no_owned_classes,
    )
    monkeypatch.setattr(
        fw.resource_access,
        "can_manage_resource",
        lambda *, resource, user, owned_class_ids: True,
    )
    monkeypatch.setattr(
        fw.resource_kind,
        "classify_many",
        lambda session, resources: {101: "quick_practice"},
    )
    monkeypatch.setattr(
        fw.layout_repo,
        "get_layout",
        lambda *, session, user_id: [
            SimpleNamespace(vmid=100, node_type="vm", position_x=11.0, position_y=22.0),
            SimpleNamespace(
                vmid=None, node_type="gateway", position_x=33.0, position_y=44.0
            ),
        ],
    )
    pve = [
        {
            "vmid": 100,
            "node": "pve1",
            "type": "qemu",
            "name": "web",
            "status": "running",
        },
        {"vmid": 101, "node": "pve1", "type": "lxc", "name": "db", "status": "stopped"},
    ]
    monkeypatch.setattr(
        fw,
        "proxmox_service",
        SimpleNamespace(
            list_all_resources=lambda: pve,
            get_ip_address=lambda node, vmid, rtype: None,
        ),
    )
    monkeypatch.setattr(
        fw.live_ip,
        "start_live_ip_probes",
        lambda resources, lookup: SimpleNamespace(collect=lambda: {100: "10.0.0.100"}),
    )
    monkeypatch.setattr(
        fw.resource_repo,
        "sync_ip_cache_many",
        lambda *, session, live_ips: {k: v or "cached" for k, v in live_ips.items()},
    )
    monkeypatch.setattr(
        fw, "get_firewall_options", lambda node, vmid, rtype: {"enable": 1}
    )
    monkeypatch.setattr(fw, "get_vm_firewall_rules", lambda node, vmid, rtype: [])
    monkeypatch.setattr(fw, "_enrich_edges_from_db", lambda edges, session: None)

    resp = fw.get_topology(user=SimpleNamespace(id="u1"), session=object())  # type: ignore[arg-type]

    by_vmid = {n.vmid: n for n in resp.nodes}
    assert set(by_vmid) == {100, 101, None}
    assert (by_vmid[100].position_x, by_vmid[100].position_y) == (11.0, 22.0)
    assert (by_vmid[101].position_x, by_vmid[101].position_y) == (100.0, 220.0)
    assert by_vmid[100].ip_address == "10.0.0.100"
    assert by_vmid[101].ip_address == "cached"
    assert by_vmid[100].can_manage is True
    assert by_vmid[101].can_manage is False
    assert (by_vmid[None].position_x, by_vmid[None].position_y) == (33.0, 44.0)
