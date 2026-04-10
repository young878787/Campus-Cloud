from __future__ import annotations

from importlib import import_module

__all__ = [
    "firewall_service",
    "gateway_service",
    "nat_service",
    "reverse_proxy_service",
    "script_deploy_service",
    "snapshot_service",
]

_MODULES = {
    "firewall_service": "app.services.infra.firewall_service",
    "gateway_service": "app.services.infra.gateway_service",
    "nat_service": "app.services.infra.nat_service",
    "reverse_proxy_service": "app.services.infra.reverse_proxy_service",
    "script_deploy_service": "app.services.infra.script_deploy_service",
    "snapshot_service": "app.services.infra.snapshot_service",
}


def __getattr__(name: str):
    if name in _MODULES:
        return import_module(_MODULES[name])
    raise AttributeError(name)
