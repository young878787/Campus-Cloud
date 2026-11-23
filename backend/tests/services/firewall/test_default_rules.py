"""firewall_service 的 setup_default_rules：預設規則的建立順序與內容，設定讀取失敗時略過額外封鎖，單一步驟失敗不影響其餘步驟。"""

from __future__ import annotations

from typing import Any

import pytest

from app.exceptions import ProxmoxError
from app.services.network import firewall_service as fw
from tests.services.firewall._fakes import FakeFirewall, _install_fw

GATEWAY_DEFAULT = "SkyLab:gateway:default"
PLATFORM_SSH = "SkyLab:platform:ssh"


# ─── setup_default_rules ────────────────────────────────────────────────────


def test_setup_default_rules_full_path(monkeypatch: pytest.MonkeyPatch) -> None:
    firewall = _install_fw(monkeypatch, FakeFirewall())
    applied: list[tuple] = []
    monkeypatch.setattr(
        fw,
        "_load_subnet_settings",
        lambda: (["10.9.0.0/16"], "10.0.0.254", "10.0.0.5"),
    )

    def fake_apply(node: str, vmid: int, rtype: str, targets: list[str]) -> dict:
        applied.append((vmid, targets))
        return {"created": targets, "updated": [], "deleted": [], "errors": []}

    monkeypatch.setattr(fw, "_apply_extra_block_rules", fake_apply)

    fw.setup_default_rules("pve1", 100, "qemu")

    assert firewall.calls[0] == (
        "options_put",
        {"enable": 1, "policy_in": "DROP", "policy_out": "ACCEPT"},
    )
    posts = [c[1] for c in firewall.calls if c[0] == "post"]
    assert posts[0]["comment"] == GATEWAY_DEFAULT
    assert [p["proto"] for p in posts[1:3]] == ["tcp", "udp"]
    assert all(p["source"] == "10.0.0.254" for p in posts[1:3])
    assert posts[3] == {
        "type": "in",
        "action": "ACCEPT",
        "source": "10.0.0.5",
        "proto": "tcp",
        "dport": "22",
        "enable": 1,
        "comment": PLATFORM_SSH,
        "pos": 0,
    }
    assert applied == [(100, ["10.9.0.0/16"])]


def test_setup_default_rules_settings_unreadable_skips_extras(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    firewall = _install_fw(monkeypatch, FakeFirewall())

    def boom() -> tuple:
        raise RuntimeError("db down")

    monkeypatch.setattr(fw, "_load_subnet_settings", boom)

    fw.setup_default_rules("pve1", 100, "lxc")

    posts = [c[1] for c in firewall.calls if c[0] == "post"]
    assert [p["comment"] for p in posts] == [GATEWAY_DEFAULT]


def test_setup_default_rules_nonfatal_step_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    firewall = _install_fw(
        monkeypatch,
        FakeFirewall(fail_post_comment="SkyLab:gateway:full-access"),
    )
    monkeypatch.setattr(
        fw, "_load_subnet_settings", lambda: (["10.9.0.0/16"], "10.0.0.254", None)
    )

    def boom(*args: Any) -> dict:
        raise RuntimeError("apply boom")

    monkeypatch.setattr(fw, "_apply_extra_block_rules", boom)

    fw.setup_default_rules("pve1", 100, "qemu")

    posts = [c[1] for c in firewall.calls if c[0] == "post"]
    assert [p["comment"] for p in posts] == [GATEWAY_DEFAULT]


def test_setup_default_rules_platform_ssh_failure_is_nonfatal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    firewall = _install_fw(monkeypatch, FakeFirewall(fail_post_comment=PLATFORM_SSH))
    monkeypatch.setattr(fw, "_load_subnet_settings", lambda: ([], None, "10.0.0.5"))

    fw.setup_default_rules("pve1", 100, "lxc")

    posts = [c[1] for c in firewall.calls if c[0] == "post"]
    assert [p["comment"] for p in posts] == [GATEWAY_DEFAULT]


def test_setup_default_rules_raises_when_options_fail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fw(monkeypatch, FakeFirewall(fail=("options_put",)))
    with pytest.raises(ProxmoxError):
        fw.setup_default_rules("pve1", 100, "qemu")
