"""Pure rubric normalization and gap-classification helpers for Teacher Judge.

Functions here are deterministic and framework-free: they only parse, repair,
and compare model-emitted candidate payloads against the persisted rubric
context and the enabled command catalog.  The chat orchestration lives in
``chat_workflow`` and transport in ``service``.
"""

from __future__ import annotations

import json
from typing import Any, Literal, cast

from app.ai.teacher_judge.automation_support import missing_step_information
from app.ai.teacher_judge.schemas import (
    TeacherJudgeRubricCheckStep,
    TeacherJudgeRubricItem,
)
from app.ai.teacher_judge.template_command_service import validate_check_steps
from app.ai.utils import safe_bool
from app.models.teacher_judge_template_command import TeacherJudgeTemplateCommand

_UNNAMED_ITEM_TITLE = "未命名項目"


def _normalize_check_steps(
    raw_steps: Any,
    template_key: str | None = None,
    template_commands: list[TeacherJudgeTemplateCommand] | None = None,
) -> list[TeacherJudgeRubricCheckStep]:
    if not isinstance(raw_steps, list):
        return []

    if template_commands is not None:
        general_command = next(
            (
                command
                for command in template_commands
                if command.command_key == "system.run_command"
            ),
            None,
        )
        canonical_steps: list[Any] = []
        for raw_step in raw_steps:
            if not isinstance(raw_step, dict):
                canonical_steps.append(raw_step)
                continue
            canonical_step = dict(raw_step)
            if (
                general_command is not None
                and str(raw_step.get("command_key") or "").strip()
                == general_command.command_key
            ):
                canonical_step["template_key"] = general_command.template_key
                raw_parameters = raw_step.get("parameters")
                parameters = (
                    dict(raw_parameters) if isinstance(raw_parameters, dict) else {}
                )
                for key in ("argv", "cwd", "timeout_seconds", "success_criteria"):
                    if key not in parameters and key in raw_step:
                        parameters[key] = raw_step[key]
                canonical_step["parameters"] = parameters
            canonical_steps.append(canonical_step)

        validated_items = validate_check_steps(
            template_key or "",
            [{"check_steps": canonical_steps}],
            template_commands,
        )
        validated_steps = [
            TeacherJudgeRubricCheckStep(**step)
            for step in validated_items[0].get("check_steps", [])
        ]
        valid_raw_references = {
            (step.template_key, step.command_key) for step in validated_steps
        }
        if general_command is None:
            return validated_steps

        recovered_steps: list[dict[str, Any]] = []
        for raw_step in canonical_steps:
            if not isinstance(raw_step, dict):
                continue
            raw_template_key = str(
                raw_step.get("template_key") or template_key or ""
            ).strip()
            raw_command_key = str(raw_step.get("command_key") or "").strip()
            if (raw_template_key, raw_command_key) in valid_raw_references:
                continue
            raw_parameters = raw_step.get("parameters")
            recovered_parameters: dict[str, Any] = (
                dict(raw_parameters) if isinstance(raw_parameters, dict) else {}
            )
            argv = recovered_parameters.get("argv")
            has_valid_argv = (
                isinstance(argv, list)
                and bool(argv)
                and all(isinstance(part, str) and part.strip() for part in argv)
            )
            if not has_valid_argv:
                continue
            for key in ("path", "file_path", "target"):
                recovered_parameters.pop(key, None)
            recovered_parameters = {
                key: value
                for key, value in recovered_parameters.items()
                if key in {"argv", "cwd", "timeout_seconds", "success_criteria"}
            }
            recovered_steps.append(
                {
                    "template_key": general_command.template_key,
                    "command_key": general_command.command_key,
                    "parameters": recovered_parameters,
                }
            )

        if recovered_steps:
            recovered_items = validate_check_steps(
                template_key or "",
                [{"check_steps": recovered_steps}],
                template_commands,
            )
            validated_steps.extend(
                TeacherJudgeRubricCheckStep(**step)
                for step in recovered_items[0].get("check_steps", [])
            )
        return validated_steps

    normalized: list[TeacherJudgeRubricCheckStep] = []
    for raw_step in raw_steps:
        if not isinstance(raw_step, dict):
            continue

        command_key = str(raw_step.get("command_key") or "").strip()
        step_template_key = str(raw_step.get("template_key") or template_key or "").strip()
        if not command_key or not step_template_key:
            continue

        command_label = raw_step.get("command_label")
        raw_parameters = raw_step.get("parameters")
        parameters = raw_parameters if isinstance(raw_parameters, dict) else {}

        normalized.append(
            TeacherJudgeRubricCheckStep(
                template_key=step_template_key,
                command_key=command_key,
                command_label=str(command_label) if command_label else None,
                parameters=parameters,
            )
        )

    return normalized


def _normalize_rubric_items(
    raw_items: Any,
    template_key: str | None = None,
    template_commands: list[TeacherJudgeTemplateCommand] | None = None,
    strip_auto_fallback: bool = True,
) -> list[TeacherJudgeRubricItem]:
    """Best-effort normalization for AI-returned item payloads."""
    if not isinstance(raw_items, list):
        return []

    normalized: list[TeacherJudgeRubricItem] = []
    for i, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            continue

        item_id = str(raw.get("id") or f"item-{i + 1}")
        title = (
            str(raw.get("title") or raw.get("name") or "").strip()
            or _UNNAMED_ITEM_TITLE
        )
        description = str(raw.get("description") or raw.get("desc") or "")
        checked = safe_bool(raw.get("checked", raw.get("is_checked")), default=False)

        raw_detectable = raw.get("detectable")
        if isinstance(raw_detectable, bool):
            detectable_raw = "auto" if raw_detectable else "manual"
        else:
            detectable_raw = str(raw_detectable or "manual").strip().lower()
        if detectable_raw not in {"auto", "partial", "manual"}:
            detectable_raw = "manual"
        detectable: Literal["auto", "partial", "manual"] = cast(
            "Literal['auto', 'partial', 'manual']", detectable_raw
        )
        judgement_mode_raw = str(raw.get("judgement_mode") or "ai").strip().lower()
        if judgement_mode_raw not in {"ai", "teacher"}:
            judgement_mode_raw = "ai"
        judgement_mode: Literal["ai", "teacher"] = cast(
            "Literal['ai', 'teacher']", judgement_mode_raw
        )

        detection_method = raw.get("detection_method") or raw.get("detection")
        fallback = raw.get("fallback") or raw.get("suggestion")
        raw_missing_information = raw.get("missing_information")
        missing_information = (
            list(
                dict.fromkeys(
                    str(value).strip()
                    for value in raw_missing_information
                    if isinstance(value, str) and value.strip()
                )
            )
            if isinstance(raw_missing_information, list)
            else []
        )
        check_steps = _normalize_check_steps(
            raw.get("check_steps"),
            template_key=template_key,
            template_commands=template_commands,
        )
        system_command_steps = [
            step for step in check_steps if step.command_key == "system.run_command"
        ]
        if system_command_steps:
            for step in system_command_steps:
                missing_information.extend(
                    missing_step_information(step, judgement_mode=judgement_mode)
                )
        if template_commands is not None and detectable == "auto" and not check_steps:
            detectable = "manual"
            missing_information = []
            detection_method = (
                str(detection_method).strip()
                if detection_method is not None
                else "目前沒有可引用的有效 command_key，缺少自動取得客觀證據的能力"
            )
            fallback = fallback or "目前平台不支援此項目的安全腳本取證。"
        if detectable == "auto" and (
            detection_method is None or not str(detection_method).strip()
        ):
            detectable = "partial"
            missing_information.append("腳本取證方式")
        if detectable == "auto":
            for step in check_steps:
                missing_information.extend(
                    missing_step_information(step, judgement_mode=judgement_mode)
                )
            if missing_information:
                detectable = "partial"
        if detectable == "partial" and not missing_information:
            missing_information.append(
                "完整的服務名稱、程式位置、連接埠、取證範圍或判定條件"
            )
        missing_information = list(dict.fromkeys(missing_information))
        if strip_auto_fallback and detectable == "auto":
            fallback = None

        normalized.append(
            TeacherJudgeRubricItem(
                id=item_id,
                title=title,
                description=description,
                checked=checked,
                detectable=detectable,
                judgement_mode=judgement_mode,
                detection_method=str(detection_method)
                if detection_method is not None
                else None,
                fallback=str(fallback) if fallback is not None else None,
                missing_information=missing_information,
                check_steps=check_steps,
            )
        )

    return normalized


def normalize_items_for_export(raw_items: Any) -> list[TeacherJudgeRubricItem]:
    """Public helper for robust export parsing."""
    # Export accepts legacy/teacher-authored payloads and must not silently
    # discard an explicitly supplied fallback while normalizing field aliases.
    return _normalize_rubric_items(raw_items, strip_auto_fallback=False)


def _rubric_context_data(rubric_context: str) -> dict[str, Any]:
    try:
        parsed = json.loads(rubric_context or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _describe_raw_candidates(raw_items: Any, rubric_context: str) -> str:
    """Summarize model-returned candidates and collisions with the current rubric."""
    if not isinstance(raw_items, list):
        return "updated_items 不是 list"
    current_items = _rubric_context_data(rubric_context).get("items")
    current_ids = {
        str(item.get("id") or "").strip()
        for item in (current_items if isinstance(current_items, list) else [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    current_titles = {
        str(item.get("title") or "").strip().casefold()
        for item in (current_items if isinstance(current_items, list) else [])
        if isinstance(item, dict) and str(item.get("title") or "").strip()
    }
    parts: list[str] = []
    for raw in raw_items[:10]:
        if not isinstance(raw, dict):
            parts.append("<非物件>")
            continue
        operation = str(raw.get("operation") or raw.get("action") or "").lower() or "無"
        item_id = str(raw.get("id") or "").strip() or "無"
        title = str(raw.get("title") or raw.get("name") or "").strip() or "無"
        flags: list[str] = []
        if operation in {"update", "delete", "remove"}:
            flags.append("宣告修改或刪除")
        if item_id != "無" and item_id in current_ids:
            flags.append("id 撞既有項目")
        if title != "無" and title.casefold() in current_titles:
            flags.append("標題撞既有項目")
        detectable = str(raw.get("detectable") or "").strip().lower()
        if detectable:
            flags.append(f"detectable={detectable}")
        suffix = f"（{'、'.join(flags)}）" if flags else ""
        parts.append(f"op={operation} id={item_id} title={title}{suffix}")
    return "; ".join(parts) if parts else "空清單"


def _proposal_requires_loaded_rubric(
    raw_items: Any,
    rubric_context: str,
    *,
    add_is_new: bool = False,
) -> bool:
    """Return whether proposal operations depend on current persisted items."""
    if not isinstance(raw_items, list):
        return False
    context_items = _rubric_context_data(rubric_context).get("items")
    current_items = (
        [item for item in context_items if isinstance(item, dict)]
        if isinstance(context_items, list)
        else []
    )
    current_ids = {
        str(item.get("id") or "").strip()
        for item in current_items
        if str(item.get("id") or "").strip()
    }
    current_titles = {
        str(item.get("title") or "").strip().casefold()
        for item in current_items
        if str(item.get("title") or "").strip()
    }
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        operation = str(raw.get("operation") or raw.get("action") or "").lower()
        item_id = str(raw.get("id") or "").strip()
        title = str(raw.get("title") or raw.get("name") or "").strip().casefold()
        if operation in {"update", "delete", "remove"}:
            return True
        if add_is_new:
            # Attachment itemwise candidates are brand-new source rows; the
            # model cannot know existing ids and id/title reuse on an add is
            # not an attempt to modify the persisted item.
            continue
        if item_id and item_id in current_ids:
            return True
        if title and title in current_titles:
            return True
    return False


def _resolve_add_candidates(raw_items: Any, rubric_context: str) -> tuple[Any, bool]:
    """Resolve add-only candidates server-side without another model round.

    Returns ``(rewritten_items, add_only)``. When every candidate is add-origin
    the backend is the source of truth for ids: a candidate colliding with an
    existing item by title (or an empty title) maps onto that item as a
    deterministic update, a fresh candidate without a usable id gets a
    server-assigned id, and a colliding id with a different title is treated as
    a guessed id for a brand-new item instead of an update. The model never
    needs to guess existing ids in this path, so the rubric-read gate is
    unnecessary.
    """
    if not isinstance(raw_items, list) or not raw_items:
        return raw_items, False
    context_items = _rubric_context_data(rubric_context).get("items")
    current_items = (
        [item for item in context_items if isinstance(item, dict)]
        if isinstance(context_items, list)
        else []
    )
    by_id = {
        str(item.get("id") or "").strip(): item
        for item in current_items
        if str(item.get("id") or "").strip()
    }
    by_title = {
        str(item.get("title") or "").strip().casefold(): item
        for item in current_items
        if str(item.get("title") or "").strip()
    }
    used_ids = set(by_id)
    add_only = True
    rewritten: list[Any] = []
    fresh_counter = 0
    for raw in raw_items:
        if not isinstance(raw, dict):
            rewritten.append(raw)
            continue
        operation = str(raw.get("operation") or raw.get("action") or "").lower()
        if operation in {"update", "delete", "remove"}:
            add_only = False
            rewritten.append(raw)
            continue
        item_id = str(raw.get("id") or "").strip()
        title = str(raw.get("title") or raw.get("name") or "").strip()
        current = by_id.get(item_id) if item_id else None
        if current is None and title:
            current = by_title.get(title.casefold())
        if current is not None:
            # A model-intended add may still collide with an existing item.
            # Matching (or empty) titles mean the candidate restates that item;
            # a colliding id with a different title is a guessed id for a
            # brand-new item and must not masquerade as an update of it.
            current_title = (
                str(current.get("title") or current.get("name") or "").strip()
            )
            if not title or title.casefold() == current_title.casefold():
                existing_id = str(current.get("id") or "").strip()
                rewritten.append({**raw, "operation": "update", "id": existing_id})
                continue
        if not item_id or item_id in used_ids:
            fresh_counter += 1
            fresh_id = f"item-new-{fresh_counter}"
            while fresh_id in used_ids:
                fresh_counter += 1
                fresh_id = f"item-new-{fresh_counter}"
            used_ids.add(fresh_id)
            rewritten.append({**raw, "operation": "add", "id": fresh_id})
            continue
        used_ids.add(item_id)
        rewritten.append({**raw, "operation": "add"})
    return rewritten, add_only


def _reassign_new_add_ids(
    raw_items: Any,
    rubric_context: str,
    *,
    coerce_to_add: bool = False,
) -> Any:
    """Give add candidates fresh ids so id reuse cannot masquerade as an update.

    With ``coerce_to_add`` (attachment itemwise mode) every candidate is a
    brand-new source row, so model-emitted update/delete operations are
    normalized to add instead of triggering a rubric read requirement.
    """
    if not isinstance(raw_items, list):
        return raw_items
    current_ids = {
        str(item.get("id") or "").strip()
        for item in _rubric_context_data(rubric_context).get("items") or []
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    rewritten: list[Any] = []
    counter = 0
    for raw in raw_items:
        if not isinstance(raw, dict):
            rewritten.append(raw)
            continue
        if coerce_to_add:
            raw = {**raw, "operation": "add"}
        raw_id = str(raw.get("id") or "").strip()
        if raw_id and raw_id not in current_ids:
            rewritten.append(raw)
            continue
        counter += 1
        fresh_id = f"item-new-{counter}"
        while fresh_id in current_ids:
            counter += 1
            fresh_id = f"item-new-{counter}"
        current_ids.add(fresh_id)
        rewritten.append({**raw, "id": fresh_id})
    return rewritten


_PROPOSAL_COMPARE_FIELDS = (
    "title",
    "description",
    "checked",
    "detectable",
    "judgement_mode",
    "detection_method",
    "fallback",
    "missing_information",
    "check_steps",
)


def _proposal_item_value(item: dict[str, Any]) -> dict[str, Any]:
    return {key: item.get(key) for key in _PROPOSAL_COMPARE_FIELDS}


def _proposal_changes(
    raw_items: Any,
    normalized_items: list[TeacherJudgeRubricItem],
    rubric_context: str,
    *,
    template_key: str,
    template_commands: list[TeacherJudgeTemplateCommand] | None,
    ready_only: bool = True,
) -> list[dict[str, Any]]:
    """Return validated changed items and explicit deletions."""
    parsed_context = _rubric_context_data(rubric_context)
    context_items = (
        parsed_context.get("items") if isinstance(parsed_context, dict) else None
    )
    normalized_context = _normalize_rubric_items(
        context_items,
        template_key=template_key,
        template_commands=template_commands,
        strip_auto_fallback=False,
    )
    current_by_id = {item.id: item.model_dump() for item in normalized_context}
    raw_dicts = (
        [item for item in raw_items if isinstance(item, dict)]
        if isinstance(raw_items, list)
        else []
    )
    changes: list[dict[str, Any]] = []

    for raw, normalized in zip(raw_dicts, normalized_items, strict=False):
        operation = str(raw.get("operation") or raw.get("action") or "").lower()
        current = current_by_id.get(normalized.id)
        if operation in {"delete", "remove"}:
            if current is not None:
                changes.append({**current, "operation": "delete"})
            continue
        if operation == "update" and current is None:
            continue
        if operation == "add" and current is not None:
            continue
        if ready_only and normalized.detectable != "auto":
            continue

        candidate = normalized.model_dump()
        if current is None:
            changes.append({**candidate, "operation": "add"})
        elif _proposal_item_value(current) != _proposal_item_value(candidate):
            changes.append({**candidate, "operation": "update"})

    return changes


def _raw_detectability_by_id(raw_items: Any) -> dict[str, str]:
    """Map normalized item ids to the model's own (lowercased) detectable value."""
    return (
        {
            str(raw.get("id") or f"item-{index + 1}"): str(
                raw.get("detectable") or ""
            )
            .strip()
            .lower()
            for index, raw in enumerate(raw_items)
            if isinstance(raw, dict)
        }
        if isinstance(raw_items, list)
        else {}
    )


_TEACHER_LOCATION_GAP_MARKERS = (
    "位置",
    "路徑",
    "目錄",
    "工作目錄",
    "檔案",
    "程式位置",
    "服務名稱",
    "連接埠",
    "Port",
    "記錄",
    "日誌",
    "範圍",
    "對象",
)
_TEACHER_RESULT_GAP_MARKERS = (
    "成功條件",
    "判定條件",
    "預期答案",
    "預期結果",
    "預期內容",
    "通過方式",
)
_TEACHER_INTERNAL_GAP_MARKERS = (
    "取證",
    "command_key",
    "argv",
    "check_steps",
    "檢查步驟",
    "檢查能力",
    "命令與參數",
    "唯讀命令",
    "逾時",
    "timeout",
    "可執行",
    "judgement_mode",
    "proposal_status",
    "detection_method",
    "missing_information",
    "template_key",
    "parameters",
    "客觀答案",
    "AI",
)

_TEACHER_INTERNAL_GAP_REWRITES = {
    "客觀成功條件": "通過方式（怎樣檢測才算正確）",
}


def _has_gap_marker(value: str, markers: tuple[str, ...]) -> bool:
    return any(marker.casefold() in value.casefold() for marker in markers)
