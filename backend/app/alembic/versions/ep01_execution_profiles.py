"""converge machine execution profiles and command catalog

Revision ID: ep01_execution_profiles
Revises: tc02_machine_job_idx
Create Date: 2026-07-29
"""

import uuid

import sqlalchemy as sa
from alembic import op

revision = "ep01_execution_profiles"
down_revision = "tc02_machine_job_idx"
branch_labels = None
depends_on = None

PROFILE_DEFAULTS = {
    "linux": ("Linux", "Linux", None, "通用 Linux 環境；先使用唯讀系統查詢確認實際發行版與服務狀態。"),
    "python": ("Python", "Python", None, "Python 執行環境；以 python3 與 python3 -m pip 進行唯讀版本及套件查詢。"),
    "n8n": (
        "n8n 1.x",
        "n8n",
        "1.x",
        "n8n 預設使用 localhost:5678；先查詢 process、port 或 HTTP 狀態，不直接修改 workflow database。",
    ),
}


def _create_old_command_table() -> None:
    op.create_table(
        "teacher_judge_template_commands",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("template_key", sa.String(50), nullable=False),
        sa.Column("command_key", sa.String(100), nullable=False),
        sa.Column("command_label", sa.String(100), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("command_template", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(30), nullable=False),
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "template_key",
            "command_key",
            name="uq_teacher_judge_template_command_key",
        ),
    )
    op.create_index(
        op.f("ix_teacher_judge_template_commands_template_key"),
        "teacher_judge_template_commands",
        ["template_key"],
    )
    op.create_index(
        op.f("ix_teacher_judge_template_commands_enabled"),
        "teacher_judge_template_commands",
        ["enabled"],
    )


def upgrade() -> None:
    op.create_table(
        "execution_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_key", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(150), nullable=False),
        sa.Column("system_name", sa.String(100), nullable=False),
        sa.Column("system_version", sa.String(50), nullable=True),
        sa.Column("manual", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_execution_profiles_profile_key"), "execution_profiles", ["profile_key"], unique=True)
    op.create_index(op.f("ix_execution_profiles_enabled"), "execution_profiles", ["enabled"])
    op.create_table(
        "execution_profile_commands",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("command_key", sa.String(100), nullable=False),
        sa.Column("command_label", sa.String(100), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("command_template", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(30), nullable=False),
        sa.Column("requires_confirmation", sa.Boolean(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["execution_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("profile_id", "command_key", name="uq_execution_profile_command_key"),
    )
    op.create_index(op.f("ix_execution_profile_commands_profile_id"), "execution_profile_commands", ["profile_id"])
    op.create_index(op.f("ix_execution_profile_commands_enabled"), "execution_profile_commands", ["enabled"])

    bind = op.get_bind()
    old_rows = bind.execute(sa.text("SELECT * FROM teacher_judge_template_commands")).mappings().all()
    profile_ids: dict[str, uuid.UUID] = {}
    for profile_key in sorted({row["template_key"] for row in old_rows} | set(PROFILE_DEFAULTS)):
        profile_id = uuid.uuid4()
        profile_ids[profile_key] = profile_id
        display_name, system_name, version, manual = PROFILE_DEFAULTS.get(
            profile_key, (profile_key, profile_key, None, "尚未提供已確認的系統手冊。")
        )
        bind.execute(
            sa.text(
                "INSERT INTO execution_profiles "
                "(id, profile_key, display_name, system_name, system_version, manual, enabled, created_at, updated_at) "
                "VALUES (:id, :key, :display, :system, :version, :manual, true, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"id": profile_id, "key": profile_key, "display": display_name, "system": system_name, "version": version, "manual": manual},
        )
    for row in old_rows:
        bind.execute(
            sa.text(
                "INSERT INTO execution_profile_commands "
                "(id, profile_id, command_key, command_label, category, command_template, description, risk_level, "
                "requires_confirmation, enabled, created_at, updated_at) "
                "VALUES (:id, :profile_id, :command_key, :command_label, :category, :command_template, :description, "
                ":risk_level, :requires_confirmation, :enabled, :created_at, :updated_at)"
            ),
            {**row, "profile_id": profile_ids[row["template_key"]]},
        )

    op.add_column("vm_templates", sa.Column("execution_profile_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_vm_templates_execution_profile", "vm_templates", "execution_profiles", ["execution_profile_id"], ["id"], ondelete="SET NULL")
    op.create_index(op.f("ix_vm_templates_execution_profile_id"), "vm_templates", ["execution_profile_id"])
    op.add_column("resources", sa.Column("execution_profile_id", sa.Uuid(), nullable=True))
    op.create_foreign_key("fk_resources_execution_profile", "resources", "execution_profiles", ["execution_profile_id"], ["id"], ondelete="SET NULL")
    op.create_index(op.f("ix_resources_execution_profile_id"), "resources", ["execution_profile_id"])
    # 只 backfill 可由穩定鍵確認的資料，不由自由文字 os_info 猜測版本。
    bind.execute(
        sa.text(
            "UPDATE vm_templates AS t SET execution_profile_id = p.id "
            "FROM execution_profiles AS p "
            "WHERE lower(t.name) = lower(p.profile_key)"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE resources AS r SET execution_profile_id = t.execution_profile_id "
            "FROM vm_templates AS t "
            "WHERE r.template_id = t.pve_vmid AND t.execution_profile_id IS NOT NULL"
        )
    )
    bind.execute(
        sa.text(
            "UPDATE resources AS r SET execution_profile_id = p.id "
            "FROM execution_profiles AS p "
            "WHERE r.execution_profile_id IS NULL "
            "AND lower(coalesce(r.service_template_slug, '')) = lower(p.profile_key)"
        )
    )
    op.drop_table("teacher_judge_template_commands")


def downgrade() -> None:
    _create_old_command_table()
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "INSERT INTO teacher_judge_template_commands "
            "(id, template_key, command_key, command_label, category, command_template, description, risk_level, "
            "requires_confirmation, enabled, created_at, updated_at) "
            "SELECT c.id, p.profile_key, c.command_key, c.command_label, c.category, c.command_template, c.description, "
            "c.risk_level, c.requires_confirmation, c.enabled, c.created_at, c.updated_at "
            "FROM execution_profile_commands c JOIN execution_profiles p ON p.id = c.profile_id"
        )
    )
    op.drop_index(op.f("ix_resources_execution_profile_id"), table_name="resources")
    op.drop_constraint("fk_resources_execution_profile", "resources", type_="foreignkey")
    op.drop_column("resources", "execution_profile_id")
    op.drop_index(op.f("ix_vm_templates_execution_profile_id"), table_name="vm_templates")
    op.drop_constraint("fk_vm_templates_execution_profile", "vm_templates", type_="foreignkey")
    op.drop_column("vm_templates", "execution_profile_id")
    op.drop_table("execution_profile_commands")
    op.drop_table("execution_profiles")
