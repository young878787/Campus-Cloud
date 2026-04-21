from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MigrationContext:
    vmid: int
    resource_type: str
    source_node: str
    target_node: str
    storage_shared: bool = False
    live_requested: bool = False


@dataclass(frozen=True)
class MigrationDecision:
    allowed: bool
    strategy: str
    reason: str | None = None
