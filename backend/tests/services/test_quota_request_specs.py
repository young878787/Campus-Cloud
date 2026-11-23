"""app/services/resource/quota_service.py 的 request_specs：LXC 使用 rootfs_size，未指定時回退佈建預設值。"""

from types import SimpleNamespace

from app.services.resource import quota_service

# ---------------------------------------------------------------------------
# 配額：尚未佈建的申請單也要佔用額度
# ---------------------------------------------------------------------------


def test_request_specs_uses_lxc_rootfs_size() -> None:
    request = SimpleNamespace(
        resource_type="lxc", cores=4, memory=8192, rootfs_size=30, disk_size=None
    )
    assert quota_service.request_specs(request) == (4, 8192, 30)


def test_request_specs_falls_back_to_provisioning_defaults() -> None:
    lxc = SimpleNamespace(
        resource_type="lxc", cores=1, memory=512, rootfs_size=None, disk_size=None
    )
    vm = SimpleNamespace(
        resource_type="qemu", cores=2, memory=2048, rootfs_size=None, disk_size=None
    )
    assert quota_service.request_specs(lxc) == (1, 512, 8)
    assert quota_service.request_specs(vm) == (2, 2048, 20)
