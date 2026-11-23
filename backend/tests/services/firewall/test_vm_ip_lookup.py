"""firewall_service 的 VM IP 查詢：即時取得失敗時回退快取，可發佈的 IP 優先採用分配紀錄。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.services.network import firewall_service as fw

# ─── VM IP 查詢 ─────────────────────────────────────────────────────────────


def test_get_vm_ip_live_without_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fw,
        "proxmox_service",
        SimpleNamespace(
            find_resource=lambda vmid: {"node": "pve1", "type": "qemu"},
            get_ip_address=lambda node, vmid, rtype: "10.0.0.5",
        ),
    )
    assert fw._get_vm_ip(100) == "10.0.0.5"


def test_get_vm_ip_falls_back_to_cache_with_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(vmid: int) -> dict:
        raise RuntimeError("pve down")

    monkeypatch.setattr(fw, "proxmox_service", SimpleNamespace(find_resource=boom))
    calls: list[tuple] = []

    def fake_sync(*, session: Any, vmid: int, live_ip: str | None) -> str:
        calls.append((vmid, live_ip))
        return "10.0.0.9"

    monkeypatch.setattr(fw.resource_repo, "sync_ip_cache", fake_sync)

    assert fw._get_vm_ip(100, session=object()) == "10.0.0.9"
    assert calls == [(100, None)]


def test_get_publishable_vm_ip_prefers_allocation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        fw.resource_repo,
        "get_allocated_ip_address",
        lambda *, session, vmid: "10.0.0.20",
    )
    monkeypatch.setattr(fw, "_get_vm_ip", lambda vmid, session=None: "10.0.0.99")

    assert fw._get_publishable_vm_ip(100, session=object()) == "10.0.0.20"


def test_get_publishable_vm_ip_allocation_error_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*, session: Any, vmid: int) -> str:
        raise RuntimeError("db error")

    monkeypatch.setattr(fw.resource_repo, "get_allocated_ip_address", boom)
    monkeypatch.setattr(fw, "_get_vm_ip", lambda vmid, session=None: "10.0.0.99")

    assert fw._get_publishable_vm_ip(100, session=object()) == "10.0.0.99"
    assert fw._get_publishable_vm_ip(100) == "10.0.0.99"
