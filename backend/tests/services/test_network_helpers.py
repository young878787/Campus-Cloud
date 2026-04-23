"""Tests for pure helpers in network services that don't need DB/SSH/Proxmox."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.network import ip_management_service as ipm
from app.services.network import nat_service as nat

# ─── ip_management_service.get_extra_blocked_subnets ────────────────────────


@dataclass
class _ConfigStub:
    extra_blocked_subnets: str | None


def test_extra_blocked_subnets_none_returns_empty() -> None:
    assert ipm.get_extra_blocked_subnets(None) == []
    assert ipm.get_extra_blocked_subnets(_ConfigStub(None)) == []
    assert ipm.get_extra_blocked_subnets(_ConfigStub("")) == []


def test_extra_blocked_subnets_splits_comma_and_newline() -> None:
    cfg = _ConfigStub("10.0.0.0/8, 192.168.0.0/16\n172.16.0.0/12")
    assert ipm.get_extra_blocked_subnets(cfg) == [
        "10.0.0.0/8",
        "192.168.0.0/16",
        "172.16.0.0/12",
    ]


def test_extra_blocked_subnets_dedups_preserving_order() -> None:
    cfg = _ConfigStub("10.0.0.0/8,10.0.0.0/8,192.168.0.0/16,10.0.0.0/8")
    assert ipm.get_extra_blocked_subnets(cfg) == ["10.0.0.0/8", "192.168.0.0/16"]


def test_extra_blocked_subnets_strips_whitespace_and_skips_empty() -> None:
    cfg = _ConfigStub(" 10.0.0.0/8 ,, , 192.168.0.0/16 ")
    assert ipm.get_extra_blocked_subnets(cfg) == ["10.0.0.0/8", "192.168.0.0/16"]


# ─── nat_service._build_haproxy_managed_block ───────────────────────────────


@dataclass
class _RuleStub:
    vmid: int
    external_port: int
    internal_port: int
    protocol: str
    vm_ip: str


def test_build_haproxy_block_empty_returns_blank() -> None:
    assert nat._build_haproxy_managed_block([]) == ""


def test_build_haproxy_block_single_rule_has_frontend_backend_pair() -> None:
    rule = _RuleStub(
        vmid=101, external_port=8080, internal_port=80, protocol="tcp",
        vm_ip="10.0.0.5",
    )
    out = nat._build_haproxy_managed_block([rule])
    assert "frontend cc-101-8080-tcp" in out
    assert "bind *:8080" in out
    assert "backend cc-101-8080-tcp-back" in out
    assert "server vm101 10.0.0.5:80 check inter 10s" in out


def test_build_haproxy_block_multiple_rules_each_get_own_section() -> None:
    rules = [
        _RuleStub(vmid=1, external_port=80, internal_port=80, protocol="tcp",
                  vm_ip="10.0.0.1"),
        _RuleStub(vmid=2, external_port=443, internal_port=443, protocol="tcp",
                  vm_ip="10.0.0.2"),
    ]
    out = nat._build_haproxy_managed_block(rules)
    assert out.count("frontend cc-") == 2
    assert "frontend cc-1-80-tcp" in out
    assert "frontend cc-2-443-tcp" in out
    # Each rule writes one `backend ...` and one `default_backend ...` (which
    # also contains the substring "backend cc-"), so 2 rules → 4 occurrences.
    assert out.count("backend cc-") == 4
