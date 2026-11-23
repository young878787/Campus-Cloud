"""app/schemas/firewall.py 的 PortSpec.protocol：正規化為小寫並去除前後空白，拒絕含換行或特殊字元、過長與空白的值。"""

import pytest
from pydantic import ValidationError

from app.schemas.firewall import PortSpec

# ---------------------------------------------------------------------------
# PortSpec.protocol
# ---------------------------------------------------------------------------


def test_port_spec_protocol_is_normalised_to_lowercase() -> None:
    assert PortSpec(port=80, protocol=" TCP ").protocol == "tcp"


@pytest.mark.parametrize("protocol", ["tcp\nfoo", "tcp;rm -rf /", "a" * 17, ""])
def test_port_spec_protocol_rejects_invalid_values(protocol: str) -> None:
    with pytest.raises(ValidationError):
        PortSpec(port=80, protocol=protocol)
