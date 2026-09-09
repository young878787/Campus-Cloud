"""Persist the active Teacher Judge rubric proposal workflow state.

Revision ID: tjprop01_persist_proposal_state
Revises: sched01_drop_dead_placement
Create Date: 2026-09-09

The proposal body already lives in assistant message metadata.  This revision
adds only the session pointer and optimistic workflow token, then performs a
conservative one-time reconciliation for pre-existing proposal messages.
"""

from __future__ import annotations

import copy
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "tjprop01_persist_proposal_state"
down_revision = "sched01_drop_dead_placement"
branch_labels = None
depends_on = None

_TABLE = "teacher_judge_sessions"


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_column(name: str) -> bool:
    return any(column["name"] == name for column in _inspector().get_columns(_TABLE))


def _has_index(name: str) -> bool:
    return any(index["name"] == name for index in _inspector().get_indexes(_TABLE))


def _as_metadata(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _reconcile_legacy_proposals(bind: sa.Connection) -> None:
    sessions = sa.table(
        _TABLE,
        sa.column("id"),
        sa.column("selected_file_id"),
        sa.column("active_proposal_message_id"),
    )
    messages = sa.table(
        "teacher_judge_session_messages",
        sa.column("id"),
        sa.column("session_id"),
        sa.column("role"),
        sa.column("message_type"),
        # Keep the JSON type here so psycopg can adapt the reconciled dict
        # when the migration writes proposal_state back to the message row.
        sa.column("metadata_json", sa.JSON()),
        sa.column("created_at"),
    )
    files = sa.table(
        "teacher_judge_files",
        sa.column("id"),
        sa.column("analysis_revision"),
    )
    file_revisions = {
        row.id: row.analysis_revision
        for row in bind.execute(sa.select(files.c.id, files.c.analysis_revision)).fetchall()
    }

    for session_row in bind.execute(
        sa.select(
            sessions.c.id,
            sessions.c.selected_file_id,
            sessions.c.active_proposal_message_id,
        )
    ).mappings():
        proposal_rows = bind.execute(
            sa.select(
                messages.c.id,
                messages.c.role,
                messages.c.message_type,
                messages.c.metadata_json,
                messages.c.created_at,
            )
            .where(messages.c.session_id == session_row["id"])
            .order_by(messages.c.created_at, messages.c.id)
        ).mappings().all()
        proposal_rows = [
            row
            for row in proposal_rows
            if str(row["role"]) in {"assistant", "TeacherJudgeMessageRole.assistant"}
            and str(row["message_type"])
            in {"rubric_proposal", "TeacherJudgeMessageType.rubric_proposal"}
        ]
        if not proposal_rows:
            continue

        current_revision = file_revisions.get(session_row["selected_file_id"])
        latest_proposal_id = proposal_rows[-1]["id"]
        latest_pending_id = None
        for row in proposal_rows:
            metadata = _as_metadata(row["metadata_json"])
            candidate_items = metadata.get("rubric_proposal")
            if not isinstance(candidate_items, list) or not candidate_items:
                continue
            state = _as_metadata(metadata.get("proposal_state"))
            base_revision = metadata.get("base_revision")
            status = (
                "pending"
                if row["id"] == latest_proposal_id
                and current_revision is not None
                and base_revision == current_revision
                else "legacy_unknown"
            )
            state.update(
                {
                    "status": status,
                    "base_revision": base_revision,
                    "candidate_items": copy.deepcopy(candidate_items),
                    "selected_item_ids": state.get("selected_item_ids", []),
                }
            )
            metadata["proposal_state"] = state
            bind.execute(
                sa.update(messages)
                .where(messages.c.id == row["id"])
                .values(metadata_json=metadata)
            )
            if status == "pending":
                # The latest eligible proposal is the only one that can be
                # safely reconstructed as active; older rows remain history.
                latest_pending_id = row["id"]

        if latest_pending_id is not None:
            bind.execute(
                sa.update(sessions)
                .where(sessions.c.id == session_row["id"])
                .values(active_proposal_message_id=latest_pending_id)
            )


def upgrade() -> None:
    if not _has_column("active_proposal_message_id"):
        op.add_column(
            _TABLE,
            sa.Column("active_proposal_message_id", sa.Uuid(), nullable=True),
        )
    if not _has_column("workflow_revision"):
        op.add_column(
            _TABLE,
            sa.Column(
                "workflow_revision",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )
    if not _has_index("ix_teacher_judge_sessions_active_proposal"):
        op.create_index(
            "ix_teacher_judge_sessions_active_proposal",
            _TABLE,
            ["active_proposal_message_id"],
        )
    _reconcile_legacy_proposals(op.get_bind())


def downgrade() -> None:
    if _has_index("ix_teacher_judge_sessions_active_proposal"):
        op.drop_index(
            "ix_teacher_judge_sessions_active_proposal",
            table_name=_TABLE,
        )
    if _has_column("workflow_revision"):
        op.drop_column(_TABLE, "workflow_revision")
    if _has_column("active_proposal_message_id"):
        op.drop_column(_TABLE, "active_proposal_message_id")
