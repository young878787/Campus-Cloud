from __future__ import annotations

from importlib import import_module

__all__ = ["resource_service"]

_MODULES = {
    "resource_service": "app.services.resource.resource_service",
}


def __getattr__(name: str):
    if name in _MODULES:
        return import_module(_MODULES[name])
    raise AttributeError(name)
