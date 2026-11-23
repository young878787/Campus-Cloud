"""firewall_service 的單台 VM 對外服務：列出並合併規則、發佈 domain 時的可用性檢查、取消發佈，以及替換服務時排除自身並於失敗時還原。"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

import app.repositories.nat_rule as nat_repo
import app.repositories.reverse_proxy as rp_repo
from app.exceptions import BadRequestError, NotFoundError, ProxmoxError
from app.schemas.firewall import (
    PortSpec,
    PublishedService,
    PublishedServiceCreate,
    PublishedServiceRef,
    TopologyEdge,
)
from app.services.network import firewall_service as fw
from app.services.network import nat_service, reverse_proxy_service

# ─── 單台 VM 對外服務 ───────────────────────────────────────────────────────


def test_list_vm_published_services_merges_rules_and_orphans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def edges_for(vmids: list[int]) -> list[TopologyEdge]:
        return [
            TopologyEdge(source_vmid=150, target_vmid=None, ports=[]),
            TopologyEdge(source_vmid=None, target_vmid=999, ports=[]),
            TopologyEdge(
                source_vmid=None,
                target_vmid=150,
                ports=[PortSpec(port=80, protocol="tcp")],
            ),
            TopologyEdge(
                source_vmid=None,
                target_vmid=150,
                ports=[PortSpec(port=80, protocol="tcp")],
            ),
        ]

    monkeypatch.setattr(fw, "get_connections_from_rules", edges_for)
    monkeypatch.setattr(fw, "_enrich_edges_from_db", lambda edges, session: None)
    monkeypatch.setattr(
        rp_repo,
        "list_rules_by_vmid",
        lambda session, vmid: [
            SimpleNamespace(
                internal_port=80,
                domain="dup.example.com",
                enable_https=True,
                allow_indexing=False,
            ),
            SimpleNamespace(
                internal_port=443,
                domain="web.example.com",
                enable_https=True,
                allow_indexing=False,
            ),
        ],
    )
    monkeypatch.setattr(
        nat_repo,
        "list_rules_by_vmid",
        lambda session, vmid: [
            SimpleNamespace(internal_port=443, protocol="tcp", external_port=8443),
            SimpleNamespace(internal_port=22, protocol="tcp", external_port=2222),
        ],
    )

    services = fw.list_vm_published_services(150, object())  # type: ignore[arg-type]

    assert [(s.port, s.mode, s.firewall_rule_present) for s in services] == [
        (22, "port_forward", False),
        (80, "firewall_only", True),
        (443, "domain", False),
    ]
    assert services[2].url == "https://web.example.com"


def test_publish_vm_service_domain_checks_availability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checked: list[str] = []
    created: list[Any] = []
    monkeypatch.setattr(fw, "list_vm_published_services", lambda vmid, session: [])
    monkeypatch.setattr(
        reverse_proxy_service,
        "assert_domain_available",
        lambda session, domain: checked.append(domain),
    )
    monkeypatch.setattr(
        fw,
        "create_connection",
        lambda **kwargs: created.append(kwargs),
    )

    result = fw.publish_vm_service(
        150,
        PublishedServiceCreate(
            port=80, mode="domain", domain="Web.Example.com", enable_https=False
        ),
        object(),  # type: ignore[arg-type]
    )

    assert checked == ["web.example.com"]
    assert created[0]["target_vmid"] == 150
    assert result.mode == "domain"
    assert result.url == "http://web.example.com"


def test_unpublish_vm_service_deletes_inbound_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(fw, "delete_connection", lambda **kwargs: calls.append(kwargs))
    session = object()

    fw.unpublish_vm_service(150, PublishedServiceRef(port=53, protocol="udp"), session)  # type: ignore[arg-type]

    assert calls[0]["source_vmid"] is None
    assert calls[0]["target_vmid"] == 150
    assert [(p.port, p.protocol) for p in calls[0]["ports"]] == [(53, "udp")]
    assert calls[0]["session"] is session


@pytest.fixture
def replace_env(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    state = SimpleNamespace(
        services=[
            PublishedService(
                port=80, protocol="tcp", mode="domain", domain="old.example.com"
            ),
            PublishedService(
                port=22, protocol="tcp", mode="port_forward", external_port=2222
            ),
        ],
        rp_rules=[],
        domain_checks=[],
        port_checks=[],
        unpublished=[],
        created=[],
        create_failures=0,
    )
    monkeypatch.setattr(
        fw, "list_vm_published_services", lambda vmid, session: state.services
    )
    monkeypatch.setattr(
        rp_repo, "list_rules_by_vmid", lambda session, vmid: state.rp_rules
    )
    monkeypatch.setattr(
        reverse_proxy_service,
        "assert_domain_available",
        lambda session, domain, exclude_rule_id=None: state.domain_checks.append(
            (domain, exclude_rule_id)
        ),
    )
    monkeypatch.setattr(
        nat_service,
        "check_port_available",
        lambda port, proto, session: state.port_checks.append((port, proto)),
    )
    monkeypatch.setattr(
        fw,
        "unpublish_vm_service",
        lambda vmid, ref, session: state.unpublished.append((ref.port, ref.protocol)),
    )

    def fake_create(**kwargs: Any) -> None:
        state.created.append(kwargs["ports"][0])
        if state.create_failures > 0:
            state.create_failures -= 1
            raise ProxmoxError("create boom")

    monkeypatch.setattr(fw, "create_connection", fake_create)
    return state


def _replace(current: PublishedServiceRef, replacement: PublishedServiceCreate) -> Any:
    return fw.replace_vm_service(150, current, replacement, object())  # type: ignore[arg-type]


def test_replace_vm_service_missing_and_conflicting(
    replace_env: SimpleNamespace,
) -> None:
    with pytest.raises(NotFoundError):
        _replace(PublishedServiceRef(port=443), PublishedServiceCreate(port=443))
    with pytest.raises(BadRequestError):
        _replace(PublishedServiceRef(port=80), PublishedServiceCreate(port=22))
    assert replace_env.unpublished == []


def test_replace_vm_service_domain_excludes_own_rule(
    replace_env: SimpleNamespace,
) -> None:
    rule_id = uuid.uuid4()
    replace_env.rp_rules = [
        SimpleNamespace(id=uuid.uuid4(), internal_port=8080, domain="old.example.com"),
        SimpleNamespace(id=rule_id, internal_port=80, domain="old.example.com"),
    ]

    result = _replace(
        PublishedServiceRef(port=80),
        PublishedServiceCreate(port=80, mode="domain", domain="old.example.com"),
    )

    assert replace_env.domain_checks == [("old.example.com", rule_id)]
    assert replace_env.unpublished == [(80, "tcp")]
    assert result.url == "https://old.example.com"


def test_replace_vm_service_restore_failure_is_logged(
    replace_env: SimpleNamespace,
) -> None:
    replace_env.create_failures = 2

    with pytest.raises(ProxmoxError):
        _replace(PublishedServiceRef(port=80), PublishedServiceCreate(port=80))

    assert len(replace_env.created) == 2
