"""Coverage for app.ai.teacher_judge.target_ip_resolver."""

from __future__ import annotations

from typing import Any

import pytest

from app.ai.teacher_judge import target_ip_resolver as svc


@pytest.fixture
def repo(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"cached": None, "allocated": None, "synced": []}
    monkeypatch.setattr(
        svc.resource_repo,
        "get_cached_ip_address",
        lambda *, session, vmid: state["cached"],
    )

    monkeypatch.setattr(
        svc.resource_repo,
        "get_allocated_ip_address",
        lambda *, session, vmid: state["allocated"] if vmid == 101 else None,
    )

    def update(*, session: Any, vmid: int, ip_address: str) -> None:
        state["synced"].append((vmid, ip_address))

    monkeypatch.setattr(svc.resource_repo, "update_ip_address", update)
    return state


def _resolve(live_resource: dict[str, Any] | None = None) -> str:
    return svc.resolve_target_ip_address(
        session=object(),  # type: ignore[arg-type]
        vmid=101,
        live_resource=live_resource,
    )


def test_cached_ip_short_circuits(repo: dict[str, Any]) -> None:
    repo["cached"] = " 10.0.0.5 "
    assert _resolve() == "10.0.0.5"


def test_find_resource_failure_returns_empty(
    repo: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(vmid: int) -> dict[str, Any]:
        raise RuntimeError("pve down")

    monkeypatch.setattr(svc.proxmox_ops, "find_resource", boom)
    assert _resolve() == ""


def test_found_resource_without_node_returns_empty(
    repo: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        svc.proxmox_ops, "find_resource", lambda vmid: {"node": "", "type": "lxc"}
    )
    assert _resolve({"node": "pve1", "type": "storage"}) == ""


def test_live_ip_lookup_failure_returns_empty(
    repo: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        svc.proxmox_ops, "find_resource", lambda vmid: {"node": "pve1", "type": "qemu"}
    )

    def boom(node: str, vmid: int, resource_type: str) -> str:
        raise RuntimeError("agent missing")

    monkeypatch.setattr(svc.proxmox_ops, "get_ip_address", boom)
    assert _resolve() == ""


def test_live_ip_blank_returns_empty(
    repo: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(svc.proxmox_ops, "get_ip_address", lambda n, v, t: "  ")
    assert _resolve({"node": "pve1", "type": "lxc"}) == ""
    assert repo["synced"] == []


def test_live_ip_is_synced_to_cache(
    repo: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(svc.proxmox_ops, "get_ip_address", lambda n, v, t: "10.1.1.1")
    assert _resolve({"node": "pve1", "type": "lxc"}) == "10.1.1.1"
    assert repo["synced"] == [(101, "10.1.1.1")]


@pytest.mark.parametrize(
    "lookup", ["empty", "blank", "ip_error", "resource_error", "missing_node"]
)
def test_unavailable_live_ip_falls_back_to_allocation_without_caching_it(
    repo: dict[str, Any], monkeypatch: pytest.MonkeyPatch, lookup: str
) -> None:
    repo["allocated"] = "10.0.0.101"

    def find(vmid: int) -> dict[str, Any]:
        assert vmid == 101
        if lookup == "resource_error":
            raise RuntimeError("pve down")
        return {"node": "" if lookup == "missing_node" else "pve1", "type": "qemu"}

    def live_ip(node: str, vmid: int, resource_type: str) -> str | None:
        assert (node, vmid, resource_type) == ("pve1", 101, "qemu")
        if lookup == "ip_error":
            raise RuntimeError("agent missing")
        return "  " if lookup == "blank" else None

    monkeypatch.setattr(svc.proxmox_ops, "find_resource", find)
    monkeypatch.setattr(svc.proxmox_ops, "get_ip_address", live_ip)

    assert _resolve() == "10.0.0.101"
    assert repo["synced"] == []
