from __future__ import annotations

from importlib import import_module

__all__ = ["provisioning_service", "proxmox_service"]

_MODULES = {
    "provisioning_service": "app.services.proxmox.provisioning_service",
    "proxmox_service": "app.infrastructure.proxmox.operations",
}


def __getattr__(name: str):
    if name in _MODULES:
        return import_module(_MODULES[name])
    raise AttributeError(name)
