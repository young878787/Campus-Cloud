"""app/services/proxmox/provisioning_service.py 的 _build_gpu_hostpci：拒絕夾帶額外 hostpci 選項、裸卡不可指定 mdev，已知 profile 正確組出 mdev 規格。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.exceptions import ProxmoxError
from app.services.proxmox import gpu_service, provisioning_service

# ---------------------------------------------------------------------------
# GPU hostpci option smuggling
# ---------------------------------------------------------------------------


def _mapping(profiles: list[Any]) -> SimpleNamespace:
    return SimpleNamespace(
        available_count=1, used_count=0, capacity_count=1, profiles=profiles
    )


def test_build_gpu_hostpci_rejects_option_smuggling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gpu_service, "get_gpu_mapping", lambda mapping_id: _mapping([]))

    with pytest.raises(ProxmoxError):
        provisioning_service._build_gpu_hostpci(
            "gpu0", "nvidia-1,romfile=/etc/passwd,rombar=0"
        )


def test_build_gpu_hostpci_rejects_profile_on_raw_passthrough_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gpu_service, "get_gpu_mapping", lambda mapping_id: _mapping([]))

    with pytest.raises(ProxmoxError):
        provisioning_service._build_gpu_hostpci("gpu0", "nvidia-1")


def test_build_gpu_hostpci_accepts_known_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = SimpleNamespace(
        mdev_type="nvidia-1", creatable=True, vram_mb=1024, name="A"
    )
    monkeypatch.setattr(
        gpu_service, "get_gpu_mapping", lambda mapping_id: _mapping([profile])
    )

    assert (
        provisioning_service._build_gpu_hostpci("gpu0", "nvidia-1")
        == "mapping=gpu0,mdev=nvidia-1"
    )
