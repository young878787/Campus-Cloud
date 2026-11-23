"""app/services/network/publish_target_policy.py 的 validate_publish_target_ip：特殊位址、基礎設施 IP 與 VM 網段限制。"""

import pytest

from app.exceptions import BadRequestError
from app.services.network.publish_target_policy import validate_publish_target_ip

# ---------------------------------------------------------------------------
# publish target IP policy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ip",
    ["127.0.0.1", "169.254.169.254", "0.0.0.0", "224.0.0.1", "255.255.255.255", "::1", "nope"],
)
def test_publish_target_rejects_special_addresses(ip: str) -> None:
    with pytest.raises(BadRequestError):
        validate_publish_target_ip(ip)


def test_publish_target_rejects_infrastructure_ips() -> None:
    with pytest.raises(BadRequestError):
        validate_publish_target_ip("10.10.0.1", blocked_ips=["10.10.0.1"])


def test_publish_target_enforces_vm_subnet_when_configured() -> None:
    with pytest.raises(BadRequestError):
        validate_publish_target_ip("192.168.1.50", allowed_cidrs=["10.10.0.0/16"])
    assert str(validate_publish_target_ip("10.10.3.7", allowed_cidrs=["10.10.0.0/16"])) == "10.10.3.7"


def test_publish_target_allows_normal_ip_without_subnet_config() -> None:
    assert str(validate_publish_target_ip("10.10.3.7")) == "10.10.3.7"
