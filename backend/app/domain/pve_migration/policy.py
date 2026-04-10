from __future__ import annotations

from app.domain.pve_migration.models import MigrationContext, MigrationDecision


def default_migration_decision(context: MigrationContext) -> MigrationDecision:
    if context.source_node == context.target_node:
        return MigrationDecision(
            allowed=False,
            strategy="noop",
            reason="source and target nodes are identical",
        )

    if context.resource_type == "lxc" and not context.live_requested:
        return MigrationDecision(
            allowed=True,
            strategy="offline-lxc",
        )

    if context.storage_shared:
        return MigrationDecision(
            allowed=True,
            strategy="shared-storage-live" if context.live_requested else "shared-storage-offline",
        )

    return MigrationDecision(
        allowed=True,
        strategy="cross-storage-offline",
    )
