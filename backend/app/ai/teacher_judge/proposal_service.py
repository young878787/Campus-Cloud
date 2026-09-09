"""Server-owned lifecycle for Teacher Judge rubric proposals.

The proposal payload remains on the assistant message so conversation history is
the single source of truth.  The session stores only a pointer to the one
currently pending proposal and a monotonic workflow revision used for
optimistic-concurrency checks.
"""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Literal, cast

import sqlalchemy as sa
from fastapi import HTTPException
from sqlmodel import Session, col, select

from app.ai.teacher_judge.schemas import (
    TeacherJudgeProposalPublic,
    TeacherJudgeProposalResolveRequest,
    TeacherJudgeProposalResolveResponse,
    TeacherJudgeRubricAnalysis,
)
from app.models.teacher_judge_file import TeacherJudgeFile
from app.models.teacher_judge_session import (
    TeacherJudgeMessageRole,
    TeacherJudgeMessageType,
    TeacherJudgeSession,
    TeacherJudgeSessionMessage,
)

PROPOSAL_STATE_KEY = "proposal_state"
PENDING = "pending"
ProposalStatus = Literal[
    "pending",
    "applied",
    "partially_applied",
    "dismissed",
    "superseded",
    "legacy_unknown",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _metadata(row: TeacherJudgeSessionMessage) -> dict[str, Any]:
    return dict(row.metadata_json) if isinstance(row.metadata_json, dict) else {}


def _candidate_items(row: TeacherJudgeSessionMessage) -> list[dict[str, Any]]:
    metadata = _metadata(row)
    state = metadata.get(PROPOSAL_STATE_KEY)
    raw_items = (
        state.get("candidate_items")
        if isinstance(state, dict)
        else metadata.get("rubric_proposal")
    )
    if not isinstance(raw_items, list):
        return []
    return [dict(item) for item in raw_items if isinstance(item, dict)]


def _state(row: TeacherJudgeSessionMessage) -> dict[str, Any]:
    metadata = _metadata(row)
    raw_state = metadata.get(PROPOSAL_STATE_KEY)
    state = dict(raw_state) if isinstance(raw_state, dict) else {}
    candidate_items = _candidate_items(row)
    state.setdefault("status", "legacy_unknown")
    state.setdefault("base_revision", metadata.get("base_revision"))
    state.setdefault("candidate_items", candidate_items)
    state.setdefault("selected_item_ids", [])
    return state


def _write_state(row: TeacherJudgeSessionMessage, state: dict[str, Any]) -> None:
    """Assign a fresh metadata dict so SQLAlchemy detects JSON changes."""

    metadata = _metadata(row)
    metadata[PROPOSAL_STATE_KEY] = deepcopy(state)
    if state.get("candidate_items") is not None:
        metadata["rubric_proposal"] = deepcopy(state["candidate_items"])
    row.metadata_json = metadata


def get_active_proposal_row(
    db: Session, item: TeacherJudgeSession
) -> TeacherJudgeSessionMessage | None:
    pointer = item.active_proposal_message_id
    if pointer is None:
        return None
    row = db.get(TeacherJudgeSessionMessage, pointer)
    if (
        row is None
        or row.session_id != item.id
        or row.role != TeacherJudgeMessageRole.assistant
        or row.message_type != TeacherJudgeMessageType.rubric_proposal
    ):
        return None
    return row if _state(row).get("status") == PENDING else None


def current_analysis_revision(db: Session, item: TeacherJudgeSession) -> int | None:
    if item.selected_file_id is None:
        return None
    file = db.get(TeacherJudgeFile, item.selected_file_id)
    return file.analysis_revision if file is not None else None


def proposal_public(
    db: Session,
    item: TeacherJudgeSession,
    row: TeacherJudgeSessionMessage | None,
) -> TeacherJudgeProposalPublic | None:
    if row is None:
        return None
    state = _state(row)
    current_revision = current_analysis_revision(db, item)
    base_revision = state.get("base_revision")
    can_apply = (
        state.get("status") == PENDING
        and base_revision == current_revision
        and current_revision is not None
    )
    status = cast(ProposalStatus, str(state.get("status") or "legacy_unknown"))
    return TeacherJudgeProposalPublic(
        message_id=str(row.id),
        status=status,
        base_revision=(
            int(base_revision) if isinstance(base_revision, int) else None
        ),
        current_revision=current_revision,
        can_apply=can_apply,
        candidate_items=deepcopy(_candidate_items(row)),
        selected_item_ids=[
            str(value)
            for value in state.get("selected_item_ids", [])
            if value is not None
        ],
        supersedes_message_id=(
            str(state["supersedes_message_id"])
            if state.get("supersedes_message_id")
            else None
        ),
        superseded_by_message_id=(
            str(state["superseded_by_message_id"])
            if state.get("superseded_by_message_id")
            else None
        ),
        result_revision=(
            int(state["result_revision"])
            if isinstance(state.get("result_revision"), int)
            else None
        ),
        resolved_at=(
            str(state["resolved_at"]) if state.get("resolved_at") else None
        ),
    )


def active_proposal_public(
    db: Session, item: TeacherJudgeSession
) -> TeacherJudgeProposalPublic | None:
    return proposal_public(db, item, get_active_proposal_row(db, item))


def proposal_context_json(
    db: Session, item: TeacherJudgeSession
) -> str:
    """Return a bounded, explicit candidate context for the next AI turn."""

    public = active_proposal_public(db, item)
    if public is None:
        return "目前沒有尚未處理的 AI 提案。"
    return json.dumps(
        {
            "message_id": public.message_id,
            "status": public.status,
            "base_revision": public.base_revision,
            "current_revision": public.current_revision,
            "candidate_items": public.candidate_items,
        },
        ensure_ascii=False,
    )


def begin_proposal(
    db: Session,
    item: TeacherJudgeSession,
    assistant: TeacherJudgeSessionMessage,
    *,
    candidate_items: list[dict[str, Any]],
    base_revision: int | None,
    supersedes: TeacherJudgeSessionMessage | None,
    expected_workflow_revision: int | None = None,
    expected_active_proposal_message_id: uuid.UUID | None = None,
) -> None:
    """Mark one candidate pending and atomically supersede the previous one.

    The request spends most of its lifetime outside a database transaction while
    waiting for the model.  When the caller supplies the starting workflow
    revision, claim the session with a conditional update before writing the
    proposal metadata.  This prevents two concurrent model responses from both
    becoming pending proposals.
    """

    if expected_workflow_revision is not None:
        pointer_condition = (
            col(TeacherJudgeSession.active_proposal_message_id).is_(None)
            if expected_active_proposal_message_id is None
            else col(TeacherJudgeSession.active_proposal_message_id)
            == expected_active_proposal_message_id
        )
        claimed = db.exec(
            sa.update(TeacherJudgeSession)
            .where(
                col(TeacherJudgeSession.id) == item.id,
                col(TeacherJudgeSession.workflow_revision)
                == expected_workflow_revision,
                pointer_condition,
            )
            .values(
                active_proposal_message_id=assistant.id,
                workflow_revision=expected_workflow_revision + 1,
                updated_at=_now(),
            )
        )
        if claimed.rowcount != 1:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "teacher_judge_context_changed",
                    "message": "檢查流程在 AI 回覆期間已更新，請重新確認目前內容。",
                },
            )
        db.refresh(item)

    if supersedes is not None:
        old_state = _state(supersedes)
        old_state.update(
            {
                "status": "superseded",
                "superseded_by_message_id": str(assistant.id),
                "resolved_at": _now().isoformat(),
            }
        )
        _write_state(supersedes, old_state)

    state = {
        "status": PENDING,
        "base_revision": base_revision,
        "candidate_items": deepcopy(candidate_items),
        "supersedes_message_id": str(supersedes.id) if supersedes else None,
        "superseded_by_message_id": None,
        "resolved_at": None,
        "resolved_by": None,
        "result_revision": None,
        "selected_item_ids": [],
    }
    _write_state(assistant, state)
    if expected_workflow_revision is None:
        item.active_proposal_message_id = assistant.id
        item.workflow_revision = int(item.workflow_revision or 0) + 1


def clear_active_proposal(
    item: TeacherJudgeSession,
    *,
    increment: bool = True,
) -> None:
    if item.active_proposal_message_id is not None:
        item.active_proposal_message_id = None
        if increment:
            item.workflow_revision = int(item.workflow_revision or 0) + 1


def _item_value(item: dict[str, Any]) -> str:
    comparable = {
        key: item.get(key)
        for key in (
            "title",
            "description",
            "checked",
            "detectable",
            "detection_method",
            "fallback",
            "missing_information",
            "check_steps",
        )
    }
    return json.dumps(comparable, ensure_ascii=False, sort_keys=True)


def proposal_changes(
    current_items: list[dict[str, Any]],
    candidate_items: list[dict[str, Any]],
) -> dict[str, tuple[str, dict[str, Any] | None]]:
    """Compute the same changed-item identity the frontend displays."""

    current_by_id = {
        str(row.get("id")): row
        for row in current_items
        if row.get("id") is not None
    }
    changes: dict[str, tuple[str, dict[str, Any] | None]] = {}
    for index, raw in enumerate(candidate_items):
        candidate = dict(raw)
        item_id = str(candidate.get("id") or f"proposal-{index}")
        operation = str(candidate.get("operation") or candidate.get("action") or "")
        if operation in {"delete", "remove"}:
            if item_id in current_by_id:
                changes[item_id] = ("delete", None)
            continue
        if item_id not in current_by_id:
            changes[item_id] = ("add", candidate)
        elif _item_value(current_by_id[item_id]) != _item_value(candidate):
            changes[item_id] = ("update", candidate)
    return changes


def _apply_changes(
    current_analysis: TeacherJudgeRubricAnalysis,
    candidate_items: list[dict[str, Any]],
    selected_item_ids: set[str],
) -> TeacherJudgeRubricAnalysis:
    current_items = [item.model_dump(mode="json") for item in current_analysis.items]
    changes = proposal_changes(current_items, candidate_items)
    invalid = selected_item_ids - set(changes)
    if invalid:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "teacher_judge_proposal_selection_invalid",
                "message": "選取的提案項目已不是目前提案內容。",
                "item_ids": sorted(invalid),
            },
        )
    next_by_id = {str(row["id"]): row for row in current_items}
    candidate_by_id = {
        str(row.get("id") or f"proposal-{index}"): row
        for index, row in enumerate(candidate_items)
    }
    for item_id in selected_item_ids:
        operation, candidate = changes[item_id]
        if operation == "delete":
            next_by_id.pop(item_id, None)
            continue
        assert candidate is not None
        clean = dict(candidate)
        clean.pop("operation", None)
        clean.pop("action", None)
        clean["id"] = item_id
        next_by_id[item_id] = clean

    # Preserve the teacher's current ordering and append newly added items in
    # the candidate order.  This avoids a partial apply unexpectedly reshuffling
    # unrelated rubric rows.
    current_ids = [str(row["id"]) for row in current_items]
    ordered = [next_by_id[item_id] for item_id in current_ids if item_id in next_by_id]
    for item_id in candidate_by_id:
        if item_id not in current_ids and item_id in next_by_id:
            ordered.append(next_by_id[item_id])
    payload = current_analysis.model_dump(mode="json")
    payload["items"] = ordered
    return TeacherJudgeRubricAnalysis.model_validate(payload)


def resolve_proposal(
    db: Session,
    item: TeacherJudgeSession,
    *,
    message_id: uuid.UUID,
    payload: TeacherJudgeProposalResolveRequest,
    resolved_by: uuid.UUID | None,
) -> TeacherJudgeProposalResolveResponse:
    """Resolve the active proposal in one transaction."""

    current_item = db.exec(
        select(TeacherJudgeSession).where(TeacherJudgeSession.id == item.id)
    ).first()
    if current_item is None:
        raise HTTPException(status_code=404, detail="找不到檢查。")
    item = current_item
    row = db.exec(
        select(TeacherJudgeSessionMessage).where(
            TeacherJudgeSessionMessage.id == message_id
        )
    ).first()
    if (
        row is None
        or row.session_id != item.id
        or item.active_proposal_message_id != message_id
        or row.role != TeacherJudgeMessageRole.assistant
        or row.message_type != TeacherJudgeMessageType.rubric_proposal
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "teacher_judge_proposal_not_active",
                "message": "這份 AI 提案已處理或不再是目前版本。",
            },
        )
    state = _state(row)
    if state.get("status") != PENDING:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "teacher_judge_proposal_not_active",
                "message": "這份 AI 提案已處理或不再是目前版本。",
            },
        )

    file = (
        db.exec(
            select(TeacherJudgeFile)
            .where(TeacherJudgeFile.id == item.selected_file_id)
        ).first()
        if item.selected_file_id
        else None
    )
    current_revision = file.analysis_revision if file else None
    if file is None or current_revision != payload.expected_analysis_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "teacher_judge_proposal_revision_conflict",
                "message": "評分表已變更，這份提案不能直接套用；請保留目前版本或請 AI 依目前內容更新。",
                "analysis_revision": current_revision,
            },
        )
    base_revision = state.get("base_revision")
    if payload.action == "apply" and base_revision != current_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "teacher_judge_proposal_revision_conflict",
                "message": "評分表已變更，這份提案不能直接套用；請保留目前版本或請 AI 依目前內容更新。",
                "analysis_revision": current_revision,
            },
        )

    selected = {str(value) for value in payload.selected_item_ids if str(value).strip()}
    candidate_items = _candidate_items(row)
    workflow_revision = int(item.workflow_revision or 0)
    if payload.action == "apply":
        changes = proposal_changes(
            [
                dict(value)
                for value in (file.analysis_json.get("items", []) if isinstance(file.analysis_json, dict) else [])
                if isinstance(value, dict)
            ],
            candidate_items,
        )
        if not selected:
            raise HTTPException(
                status_code=422,
                detail="至少選取一個 AI 提案項目，或選擇保留目前版本。",
            )
        invalid = selected - set(changes)
        if invalid:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "teacher_judge_proposal_selection_invalid",
                    "message": "選取的提案項目已不是目前提案內容。",
                    "item_ids": sorted(invalid),
                },
            )
        current_analysis = TeacherJudgeRubricAnalysis.model_validate(file.analysis_json)
        next_analysis = _apply_changes(current_analysis, candidate_items, selected)
        result_revision = int(current_revision or 1) + 1
        file_update = db.exec(
            sa.update(TeacherJudgeFile)
            .where(
                col(TeacherJudgeFile.id) == file.id,
                col(TeacherJudgeFile.analysis_revision) == current_revision,
            )
            .values(
                analysis_json=next_analysis.model_dump(mode="json"),
                analysis_revision=result_revision,
                updated_at=_now(),
            )
        )
        if file_update.rowcount != 1:
            db.rollback()
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "teacher_judge_proposal_revision_conflict",
                    "message": "評分表已變更，這份提案不能直接套用；請保留目前版本或請 AI 依目前內容更新。",
                },
            )
        state["status"] = "applied" if selected == set(changes) else "partially_applied"
    else:
        if selected:
            raise HTTPException(status_code=422, detail="保留目前版本不接受提案項目。")
        state["status"] = "dismissed"
        result_revision = current_revision

    state.update(
        {
            "selected_item_ids": sorted(selected),
            "resolved_at": _now().isoformat(),
            "resolved_by": str(resolved_by) if resolved_by else None,
            "result_revision": result_revision,
        }
    )
    _write_state(row, state)
    now = _now()
    resolved = db.exec(
        sa.update(TeacherJudgeSession)
        .where(
            col(TeacherJudgeSession.id) == item.id,
            col(TeacherJudgeSession.active_proposal_message_id) == message_id,
            col(TeacherJudgeSession.workflow_revision) == workflow_revision,
        )
        .values(
            active_proposal_message_id=None,
            workflow_revision=workflow_revision + 1,
            updated_at=now,
            last_activity_at=now,
        )
    )
    if resolved.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "teacher_judge_proposal_not_active",
                "message": "這份 AI 提案已處理或不再是目前版本。",
            },
        )
    db.add(row)
    db.commit()
    db.refresh(item)
    db.refresh(row)
    db.refresh(file)
    return TeacherJudgeProposalResolveResponse(
        message_id=str(message_id),
        status=cast(ProposalStatus, str(state["status"])),
        analysis_revision=result_revision,
        workflow_revision=int(item.workflow_revision or 0),
        active_proposal_message_id=None,
        selected_item_ids=sorted(selected),
        analysis_json=deepcopy(file.analysis_json) if payload.action == "apply" else None,
    )


__all__ = [
    "PENDING",
    "active_proposal_public",
    "begin_proposal",
    "clear_active_proposal",
    "current_analysis_revision",
    "get_active_proposal_row",
    "proposal_changes",
    "proposal_context_json",
    "proposal_public",
    "resolve_proposal",
]
