from __future__ import annotations

import pytest

from app.exceptions import BadRequestError
from app.services.network import gateway_service


def test_build_traefik_static_config_uses_dns_challenge() -> None:
    config = gateway_service.build_traefik_static_config(
        acme_email="ops@example.com"
    )

    assert "dnsChallenge:" in config
    assert "provider: cloudflare" in config
    assert "httpChallenge" not in config
    assert 'address: "127.0.0.1:8080"' in config
    assert "dashboard: true" in config


def test_build_traefik_env_file_rejects_multiline_token() -> None:
    with pytest.raises(BadRequestError, match="Cloudflare API Token 格式不正確"):
        gateway_service.build_traefik_env_file("line1\nline2")


def test_build_traefik_env_file_quotes_cloudflare_token() -> None:
    env_file = gateway_service.build_traefik_env_file('cf-token"with$chars')

    assert 'CF_DNS_API_TOKEN="cf-token\\"with\\$chars"' in env_file


def test_build_traefik_systemd_unit_loads_environment_file() -> None:
    unit = gateway_service.build_traefik_systemd_unit()

    assert f"EnvironmentFile=-{gateway_service.TRAEFIK_ENV_PATH}" in unit
    assert "ExecStart=/usr/local/bin/traefik --configFile=/etc/traefik/traefik.yml" in unit


def test_parse_detected_service_versions() -> None:
    install_targets = {
        "traefik": "3.3.4",
        "frps": "0.62.0",
        "frpc": "0.62.0",
    }

    traefik_info = gateway_service._build_service_version_info(
        service="traefik",
        version_output="Version:      3.3.4\nCodename:     ramequin",
        install_targets=install_targets,
        candidate_version=None,
    )
    haproxy_info = gateway_service._build_service_version_info(
        service="haproxy",
        version_output="HAProxy version 2.6.12-1+deb12u2 2024/10/01 - https://haproxy.org/",
        install_targets=install_targets,
        candidate_version="2.8.10-1~deb12u1",
    )

    assert traefik_info.current_version == "3.3.4"
    assert traefik_info.target_version == "3.3.4"
    assert traefik_info.update_available is False
    assert haproxy_info.current_version == "2.6.12-1+deb12u2"
    assert haproxy_info.target_version == "2.8.10-1~deb12u1"
    assert haproxy_info.update_available is True
