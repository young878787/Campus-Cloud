"""Backfill Resource execution facts for every provisioning path.

Revision ID: ep03_resource_execution
Revises: ep02_profile_key_index
Create Date: 2026-07-29
"""

import uuid

import sqlalchemy as sa
from alembic import op

revision = "ep03_resource_execution"
down_revision = "ep02_profile_key_index"
branch_labels = None
depends_on = None

GENERIC_PROFILES = {
    "vm-generic": (
        "Generic VM",
        "VM",
        "這是 QEMU 虛擬機器；作業系統與版本尚未確認。僅能依一般 VM 邊界提供建議，先使用唯讀查詢確認 guest OS。",
    ),
    "lxc-generic": (
        "Generic LXC",
        "LXC",
        "這是 LXC 容器；發行版與版本尚未確認。先使用唯讀查詢確認 /etc/os-release，不假設 systemd 一定可用。",
    ),
    "unknown-generic": (
        "Unknown managed resource",
        "Managed resource",
        "資源類型與作業系統尚未確認。不得猜測 VM、LXC、發行版或版本，需由管理者補齊設定。",
    ),
}


def upgrade() -> None:
    bind = op.get_bind()
    op.add_column(
        "resources",
        sa.Column(
            "resource_type",
            sa.String(length=10),
            nullable=True,
            server_default="unknown",
        ),
    )
    op.create_index(
        op.f("ix_resources_resource_type"),
        "resources",
        ["resource_type"],
    )

    for profile_key, (display_name, system_name, manual) in GENERIC_PROFILES.items():
        exists = bind.execute(
            sa.text(
                "SELECT 1 FROM execution_profiles WHERE profile_key = :profile_key"
            ),
            {"profile_key": profile_key},
        ).first()
        if exists:
            continue
        bind.execute(
            sa.text(
                "INSERT INTO execution_profiles "
                "(id, profile_key, display_name, system_name, system_version, "
                "manual, enabled, created_at, updated_at) "
                "VALUES (:id, :profile_key, :display_name, :system_name, NULL, "
                ":manual, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {
                "id": uuid.uuid4(),
                "profile_key": profile_key,
                "display_name": display_name,
                "system_name": system_name,
                "manual": manual,
            },
        )

    # Prefer the creation source-of-truth. VM102-like batch resources are
    # resolved from batch_provision_jobs.resource_type without querying guests.
    bind.execute(
        sa.text(
            "UPDATE resources AS r SET resource_type = "
            "CASE WHEN lower(v.resource_type) = 'lxc' THEN 'lxc' ELSE 'qemu' END "
            "FROM vm_requests AS v "
            "WHERE r.request_id = v.id"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE resources AS r SET resource_type = "
            "CASE WHEN lower(b.resource_type) = 'lxc' THEN 'lxc' ELSE 'qemu' END "
            "FROM batch_provision_jobs AS b "
            "WHERE r.batch_job_id = b.id"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE resources SET resource_type = 'qemu' "
            "WHERE resource_type = 'unknown' AND template_id IS NOT NULL"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE resources SET resource_type = 'lxc' "
            "WHERE resource_type = 'unknown' AND service_template_slug IS NOT NULL"
        )
    )

    bind.execute(
        sa.text(
            "UPDATE resources AS r SET os_info = v.os_info "
            "FROM vm_requests AS v "
            "WHERE r.request_id = v.id AND r.os_info IS NULL "
            "AND v.os_info IS NOT NULL AND btrim(v.os_info) <> ''"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE resources SET os_info = service_template_slug "
            "WHERE os_info IS NULL AND service_template_slug IS NOT NULL "
            "AND btrim(service_template_slug) <> ''"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE resources SET os_info = CASE resource_type "
            "WHEN 'qemu' THEN 'VM（作業系統未確認）' "
            "WHEN 'lxc' THEN 'LXC（作業系統未確認）' "
            "ELSE '受管資源（類型與作業系統未確認）' END "
            "WHERE os_info IS NULL OR btrim(os_info) = ''"
        )
    )

    bind.execute(
        sa.text(
            "UPDATE resources AS r SET execution_profile_id = t.execution_profile_id "
            "FROM vm_templates AS t "
            "WHERE r.execution_profile_id IS NULL "
            "AND r.template_id = t.pve_vmid "
            "AND t.execution_profile_id IS NOT NULL"
        )
    )
    for profile_key, pattern in (
        ("n8n", "%n8n%"),
        ("python", "%python%"),
        ("linux", "%linux%"),
        ("linux", "%debian%"),
        ("linux", "%ubuntu%"),
        ("linux", "%alpine%"),
        ("linux", "%centos%"),
        ("linux", "%fedora%"),
        ("linux", "%rocky%"),
        ("linux", "%alma%"),
    ):
        bind.execute(
            sa.text(
                "UPDATE resources AS r SET execution_profile_id = p.id "
                "FROM execution_profiles AS p "
                "WHERE r.execution_profile_id IS NULL "
                "AND p.profile_key = :profile_key "
                "AND lower(coalesce(r.os_info, '') || ' ' || "
                "coalesce(r.service_template_slug, '')) LIKE :pattern"
            ),
            {"profile_key": profile_key, "pattern": pattern},
        )
    bind.execute(
        sa.text(
            "UPDATE resources AS r SET execution_profile_id = p.id "
            "FROM execution_profiles AS p "
            "WHERE r.execution_profile_id IS NULL "
            "AND p.profile_key = CASE r.resource_type "
            "WHEN 'qemu' THEN 'vm-generic' "
            "WHEN 'lxc' THEN 'lxc-generic' "
            "ELSE 'unknown-generic' END"
        )
    )

    op.alter_column(
        "resources",
        "resource_type",
        existing_type=sa.String(length=10),
        nullable=False,
        server_default="unknown",
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "UPDATE resources SET execution_profile_id = NULL "
            "WHERE execution_profile_id IN ("
            "SELECT id FROM execution_profiles "
            "WHERE profile_key IN ('vm-generic', 'lxc-generic', 'unknown-generic'))"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE resources SET os_info = NULL "
            "WHERE os_info IN ("
            "'VM（作業系統未確認）', "
            "'LXC（作業系統未確認）', "
            "'受管資源（類型與作業系統未確認）')"
        )
    )
    bind.execute(
        sa.text(
            "DELETE FROM execution_profiles "
            "WHERE profile_key IN ('vm-generic', 'lxc-generic', 'unknown-generic')"
        )
    )
    op.drop_index(op.f("ix_resources_resource_type"), table_name="resources")
    op.drop_column("resources", "resource_type")
