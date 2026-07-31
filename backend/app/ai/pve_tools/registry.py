"""Explicit registry and template profiles for guest checks."""

from __future__ import annotations

from app.ai.pve_tools.checks.common import COMMON_CHECKS
from app.ai.pve_tools.checks.n8n import N8N_CHECKS
from app.ai.pve_tools.checks.postgresql import POSTGRESQL_CHECKS
from app.ai.pve_tools.checks.python import PYTHON_CHECKS
from app.ai.pve_tools.schemas import CheckDefinition, ResolvedProfile

_CHECKS = COMMON_CHECKS + N8N_CHECKS + PYTHON_CHECKS + POSTGRESQL_CHECKS
CHECK_REGISTRY: dict[str, CheckDefinition] = {check.key: check for check in _CHECKS}
if len(CHECK_REGISTRY) != len(_CHECKS):
    raise RuntimeError("AI PVE check registry contains duplicate check keys")

_PROFILE_KEYS: dict[str, tuple[str, ...]] = {
    "n8n": (
        "system.disk_usage",
        "service.process_search",
        "n8n.port_5678",
        "n8n.local_http",
    ),
    "python": (
        "system.disk_usage",
        "python.version",
        "python.environment",
        "python.processes",
        "python.listening_ports",
    ),
    "postgresql": (
        "system.disk_usage",
        "postgresql.version",
        "postgresql.readiness",
        "postgresql.service_status",
        "postgresql.port_5432",
    ),
}


def resolve_profile(template_key: str) -> ResolvedProfile:
    keys = _PROFILE_KEYS.get(template_key, ())
    missing = [key for key in keys if key not in CHECK_REGISTRY]
    if missing:
        raise RuntimeError(
            f"AI PVE profile {template_key!r} references unknown checks: {missing}"
        )
    return ResolvedProfile(
        template_key=template_key,
        checks=tuple(CHECK_REGISTRY[key] for key in keys),
    )
