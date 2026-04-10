from __future__ import annotations

from importlib import import_module

__all__ = ["vm_request_schedule_service"]

_MODULES = {
    "vm_request_schedule_service": "app.services.scheduling.coordinator",
}


def __getattr__(name: str):
    if name in _MODULES:
        return import_module(_MODULES[name])
    raise AttributeError(name)
