"""Public schemas for AI Teacher Judge workflows.

Canonical names use the ``TeacherJudge`` prefix so API contracts are easy to
trace back to this feature. Legacy ``Rubric*`` aliases are kept at the bottom
for older import paths and generated-client compatibility during migration.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal, cast

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_serializer,
    model_validator,
)

from app.ai.teacher_judge.template_command_service import (
    DEFAULT_SYSTEM_COMMAND_TIMEOUT_SECONDS,
    SUPPORTED_TEMPLATE_KEYS,
    sanitize_check_step_parameters,
)
from app.core.i18n import t

_RETIRED_RUBRIC_GAP_MARKERS = (
    "success_criteria",
    "成功條件",
    "客觀成功條件",
    "判定條件",
)


def sanitize_rubric_missing_information(value: Any) -> Any:
    """Ignore obsolete standalone result-condition gaps from old rubrics."""
    if not isinstance(value, list):
        return value
    return [
        entry
        for entry in value
        if not (
            isinstance(entry, str)
            and any(
                marker.casefold() in entry.casefold()
                for marker in _RETIRED_RUBRIC_GAP_MARKERS
            )
        )
    ]


class TeacherJudgeRubricCollector(BaseModel):
    """Validated shape for one deterministic evidence collector.

    The compiler performs the security and cross-field checks.  Keeping the
    public model deliberately small lets old rubric rows continue to deserialize
    while exposing the typed v1 contract to new callers.
    """

    type: Literal[
        "command", "file_text", "file_stat", "localhost_http", "peer_ping"
    ]
    argv: list[str] | None = None
    cwd: str | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=300)
    path: str | None = None
    read_mode: Literal["full", "head", "tail"] | None = None
    lines: int | None = Field(default=None, ge=1, le=10_000)
    max_chars: int | None = Field(default=None, ge=1, le=12_000)
    encoding: str | None = None
    method: Literal["GET", "HEAD"] | None = None
    url: str | None = None

    @model_validator(mode="before")
    @classmethod
    def apply_safe_defaults(cls, value: Any) -> Any:
        """Fill server-owned limits that teachers and models need not repeat."""

        if not isinstance(value, dict):
            return value
        data = dict(value)
        collector_type = str(data.get("type") or "").strip()
        if collector_type in {"command", "peer_ping", "localhost_http"}:
            data.setdefault(
                "timeout_seconds", DEFAULT_SYSTEM_COMMAND_TIMEOUT_SECONDS
            )
        if collector_type == "file_text":
            data.setdefault("read_mode", "full")
            data.setdefault("max_chars", 12_000)
            data.setdefault("encoding", "utf-8")
        elif collector_type == "localhost_http":
            data.setdefault("method", "GET")
            data.setdefault("max_chars", 12_000)
        return data

    @model_validator(mode="after")
    def validate_required_fields(self) -> TeacherJudgeRubricCollector:
        if self.type == "command":
            if not self.argv or any(not part.strip() for part in self.argv):
                raise ValueError("command collector requires non-empty argv")
            if self.timeout_seconds is None:
                raise ValueError("command collector requires timeout_seconds")
        elif self.type == "file_text":
            if not self.path or self.read_mode is None or self.max_chars is None:
                raise ValueError(
                    "file_text collector requires path/read_mode/max_chars"
                )
            if self.read_mode in {"head", "tail"} and self.lines is None:
                raise ValueError("head/tail file_text collector requires lines")
        elif self.type == "file_stat" and not self.path:
            raise ValueError("file_stat collector requires path")
        elif self.type == "localhost_http":
            if (
                self.method is None
                or not self.url
                or self.timeout_seconds is None
                or self.max_chars is None
            ):
                raise ValueError(
                    "localhost_http collector requires method/url/timeout_seconds/max_chars"
                )
        elif self.type == "peer_ping" and self.timeout_seconds is None:
            raise ValueError("peer_ping collector requires timeout_seconds")
        return self


class TeacherJudgeRubricAssertion(BaseModel):
    """Deterministic assertion applied to a collector observation."""

    type: Literal[
        "returncode_equals",
        "text_equals",
        "text_contains",
        "number_compare",
        "json_path_equals",
        "exists",
    ]
    expected: Any = None
    operator: Literal["eq", "ne", "gt", "gte", "lt", "lte"] | None = None
    path: str | None = None
    normalize: Literal["strip"] | None = None
    case_sensitive: bool = True


class TeacherJudgeRubricCheckStep(BaseModel):
    """Canonical executable step with a read-compatible legacy shape.

    New data uses typed ``collector``/``assertion`` fields. The old flat and
    template/command catalog fields remain optional so persisted rubrics can be
    read and converted without making the retired keys part of typed writes.
    """

    id: str | None = Field(default=None, description="typed check ID；同一份 plan 內唯一")
    title: str | None = Field(default=None, description="typed check 顯示名稱")
    collector: TeacherJudgeRubricCollector | None = Field(
        default=None,
        description="typed deterministic evidence collector",
    )
    assertion: TeacherJudgeRubricAssertion | None = Field(
        default=None,
        description="typed deterministic assertion；teacher mode 省略",
    )
    template_key: str | None = Field(
        default=None,
        description="Legacy template key; read/convert only",
    )
    command_key: str | None = Field(
        default=None,
        description="Legacy command catalog key; read/convert only",
    )
    command_label: str | None = Field(
        default=None,
        description="Legacy command display name",
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Legacy nested execution parameters",
    )
    argv: list[str] | None = Field(
        default=None,
        min_length=1,
        description="單一受控命令的 argv；新 contract 的必要執行資料",
    )
    cwd: str | None = Field(
        default=None,
        description="受控命令的工作目錄；需要時填寫",
    )
    timeout_seconds: int | None = Field(
        default=None,
        ge=1,
        le=300,
        description="受控命令逾時秒數",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_flat_parameters(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        raw_parameters = data.get("parameters")
        parameters = dict(raw_parameters) if isinstance(raw_parameters, dict) else {}
        for key in ("argv", "cwd", "timeout_seconds"):
            if key in data and data[key] is not None:
                parameters.setdefault(key, data[key])
        if parameters:
            data["parameters"] = parameters
        if not data.get("template_key") and not data.get("command_key"):
            for key in ("argv", "cwd", "timeout_seconds"):
                if key not in data:
                    data[key] = parameters.get(key)
        return data

    @field_validator("parameters", mode="before")
    @classmethod
    def _drop_retired_parameters(cls, value: Any) -> Any:
        return sanitize_check_step_parameters(value)

    @field_validator("argv")
    @classmethod
    def validate_flat_argv(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        if any(not part.strip() for part in value):
            raise ValueError("argv 必須只包含非空字串")
        return value

    @model_validator(mode="after")
    def require_legacy_identity_or_flat_argv(self) -> TeacherJudgeRubricCheckStep:
        if self.collector is not None:
            if not self.id or not self.id.strip():
                raise ValueError("typed check step requires id")
            return self
        if not self.template_key and not self.command_key and self.argv is None:
            raise ValueError("flat check step requires argv")
        return self

    @model_serializer(mode="plain")
    def _serialize_contract(self) -> dict[str, Any]:
        if self.collector is not None:
            typed_serialized: dict[str, Any] = {
                "id": self.id,
                "collector": self.collector.model_dump(mode="json", exclude_none=True),
            }
            if self.title is not None:
                typed_serialized["title"] = self.title
            if self.assertion is not None:
                typed_serialized["assertion"] = self.assertion.model_dump(
                    mode="json", exclude_none=True
                )
            return typed_serialized
        if self.template_key or self.command_key:
            legacy_serialized = {
                "template_key": self.template_key,
                "command_key": self.command_key,
                "parameters": self.parameters,
            }
            if self.command_label is not None:
                legacy_serialized["command_label"] = self.command_label
            return legacy_serialized
        flat_serialized: dict[str, Any] = {}
        if self.argv is not None:
            flat_serialized["argv"] = self.argv
        if self.cwd is not None:
            flat_serialized["cwd"] = self.cwd
        if self.timeout_seconds is not None:
            flat_serialized["timeout_seconds"] = self.timeout_seconds
        return flat_serialized

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: Any,
        handler: Any,
    ) -> dict[str, Any]:
        """Expose typed and flat write contracts, hiding retired fields."""
        schema = handler(core_schema)
        properties = schema.get("properties")
        if isinstance(properties, dict):
            for legacy_key in (
                "template_key",
                "command_key",
                "command_label",
                "parameters",
            ):
                properties.pop(legacy_key, None)
            typed_properties = {
                key: properties.pop(key)
                for key in ("id", "title", "collector", "assertion")
                if key in properties
            }
            schema["properties"] = properties
            schema["anyOf"] = [
                {"required": ["argv"]},
                {
                    "type": "object",
                    "properties": typed_properties,
                    "required": ["id", "collector"],
                },
            ]
            schema.pop("required", None)
        return cast("dict[str, Any]", schema)


class TeacherJudgeRubricItem(BaseModel):
    """單一檢查項目。"""

    id: str = Field(..., description="檢查項目唯一 ID")
    title: str = Field(..., description="檢查項目名稱")
    checked: bool = Field(default=False, description="是否已確認")
    detectable: Literal["auto", "partial", "manual"] = Field(
        default="manual",
        description="腳本取證支援：auto=可執行取證、partial=缺少資訊、manual=不支援",
    )
    judgement_mode: Literal["system", "ai", "teacher"] = Field(
        default="ai",
        description=(
            "結果核對方式：system=系統固定 assertion、"
            "teacher=導師依腳本證據核查、ai=舊資料相容名稱"
        ),
    )
    detection_method: str | None = Field(
        default=None,
        description="腳本取證方式說明（detectable=auto/partial 時填寫）",
    )
    fallback: str | None = Field(
        default=None,
        description="無法自動偵測時的替代建議",
    )
    missing_information: list[str] = Field(
        default_factory=list,
        description="目前尚缺、補齊後才可能產生並執行取證腳本的資訊。",
    )
    target_node_key: str | None = Field(
        default=None,
        max_length=80,
        description=(
            "班級內的邏輯機器身份；P1/P2/P3 僅為顯示標籤，不能取代 node_key。"
        ),
    )
    peer_node_key: str | None = Field(
        default=None,
        max_length=80,
        description=(
            "選填；由 target_node_key 執行節點觀察的同班級邏輯機器身份。"
            "P1/P2/P3 僅為輸入與顯示別名。"
        ),
    )

    @field_validator("missing_information", mode="before")
    @classmethod
    def _drop_retired_gaps(cls, value: Any) -> Any:
        return sanitize_rubric_missing_information(value)
    check_steps: list[TeacherJudgeRubricCheckStep] = Field(
        default_factory=list,
        description="本階段只產生計劃書；新資料使用扁平 argv/cwd/timeout，不代表已執行。",
    )


class TeacherJudgeRubricAnalysis(BaseModel):
    """AI 核對檢查表後的結構化結果。"""

    items: list[TeacherJudgeRubricItem] = Field(default_factory=list)
    total_items: int = Field(default=0)
    checked_count: int = Field(default=0)
    auto_count: int = Field(default=0)
    partial_count: int = Field(default=0)
    manual_count: int = Field(default=0)
    detectability_needs_review: bool = Field(
        default=False,
        description="檢查項目異動後，既有證據收集支援是否需要重新核查。",
    )
    pending_review_item_ids: list[str] = Field(
        default_factory=list,
        description="尚未重新確認證據收集支援的檢查項目 ID。",
    )
    summary: str = Field(default="", description="AI 整體說明（繁體中文）")


class TeacherJudgeRubricChatMessage(BaseModel):
    """對話訊息。"""

    role: Literal["user", "assistant"] = Field(..., description="'user' 或 'assistant'")
    content: str = Field(..., description="訊息內容")


class TeacherJudgeRubricExportRequest(BaseModel):
    """匯出 Excel 請求。"""

    items: list[dict[str, Any]] = Field(..., min_length=1)
    summary: str = Field(default="")


TeacherJudgeFileStatusLiteral = Literal["active", "replaced"]
TeacherJudgeScriptLanguageLiteral = Literal["python", "shell", "bat"]
TeacherJudgeScriptSourceLiteral = Literal["ai_generated", "regenerated"]
TeacherJudgeScriptStatusLiteral = Literal[
    "draft", "review_failed", "reviewed", "approved", "archived"
]
TeacherJudgeScriptRunTargetScopeLiteral = Literal[
    "all_students_on_node", "all_with_vm", "running_only", "manual"
]
TeacherJudgeScriptRunStatusLiteral = Literal[
    "pending", "running", "completed", "failed", "cancelled"
]
TeacherJudgeSessionStatusLiteral = Literal["active", "archived"]
TeacherJudgeAttachmentStatusLiteral = Literal["ready", "failed"]
TeacherJudgeMessageRoleLiteral = Literal["user", "assistant"]
TeacherJudgeMessageTypeLiteral = Literal["chat", "rubric_proposal", "system_notice"]
TeacherJudgeSessionCreationModeLiteral = Literal["blank", "existing"]
TeacherJudgeFileSourceTypeLiteral = Literal["uploaded", "created"]


class TeacherJudgeSessionCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    teaching_class_week_id: uuid.UUID | None = None
    selected_file_id: uuid.UUID | None = None
    creation_mode: TeacherJudgeSessionCreationModeLiteral | None = None
    rubric_name: str | None = Field(default=None, max_length=255)
    environment_keys: list[str] | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError(t("schemas.title_blank"))
        return title

    @field_validator("rubric_name")
    @classmethod
    def validate_rubric_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        name = value.strip()
        if not name:
            raise ValueError(t("schemas.rubric_name_blank"))
        return name

    @field_validator("environment_keys")
    @classmethod
    def normalize_environment_keys(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = list(
            dict.fromkeys(str(key).strip().lower() for key in value if str(key).strip())
        )
        if any(key not in SUPPORTED_TEMPLATE_KEYS for key in normalized):
            raise ValueError(t("schemas.environment_keys_unsupported"))
        return normalized

    def model_post_init(self, __context: Any) -> None:
        # ``creation_mode=None`` intentionally preserves the legacy contract:
        # callers may create a session with only title/selected_file_id.
        if self.creation_mode == "blank":
            if self.selected_file_id is not None:
                raise ValueError(t("schemas.blank_creation_no_file"))
            if not self.rubric_name:
                raise ValueError(t("schemas.blank_creation_requires_rubric_name"))
        elif self.creation_mode == "existing":
            if self.selected_file_id is None:
                raise ValueError(t("schemas.existing_creation_requires_file"))
            if self.rubric_name is not None or self.environment_keys is not None:
                raise ValueError(t("schemas.existing_creation_no_blank_fields"))


class TeacherJudgeSessionUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    teaching_class_week_id: uuid.UUID | None = None
    selected_file_id: uuid.UUID | None = None
    status: TeacherJudgeSessionStatusLiteral | None = None
    is_pinned: bool | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        title = value.strip()
        if not title:
            raise ValueError(t("schemas.title_blank"))
        return title


class TeacherJudgeSessionPublic(BaseModel):
    id: str
    teaching_class_id: str
    teaching_class_week_id: str | None = None
    title: str
    status: TeacherJudgeSessionStatusLiteral
    selected_file_id: str | None
    selected_file_name: str | None = None
    selected_file_item_count: int | None = None
    template_key: str | None = None
    summary: str
    message_count: int = 0
    script_count: int = 0
    run_count: int = 0
    created_by: str | None
    created_at: str
    updated_at: str
    last_activity_at: str
    pinned_at: str | None = None


class TeacherJudgeSessionMessageCreateRequest(BaseModel):
    content: str = Field(default="", max_length=20000)
    analysis_revision: int | None = Field(default=None, ge=1)
    attachment_ids: list[uuid.UUID] = Field(default_factory=list, max_length=5)
    is_refine: bool = Field(
        default=False,
        description="True = 以目前檢查表執行整表潤飾",
    )


class TeacherJudgeSessionMessagePublic(BaseModel):
    id: str
    session_id: str
    role: TeacherJudgeMessageRoleLiteral
    content: str
    message_type: TeacherJudgeMessageTypeLiteral
    metadata_json: dict[str, Any]
    attachments: list[TeacherJudgeSessionAttachmentPublic] = Field(default_factory=list)
    created_by: str | None
    created_at: str


class TeacherJudgeSessionChatResponse(BaseModel):
    user_message: TeacherJudgeSessionMessagePublic
    assistant_message: TeacherJudgeSessionMessagePublic
    rubric_proposal: list[dict[str, Any]] | None = None
    base_revision: int | None = None


class TeacherJudgeSessionAttachmentPublic(BaseModel):
    id: str
    session_id: str
    message_id: str | None = None
    original_filename: str
    media_type: str | None = None
    size_bytes: int
    file_hash: str
    status: TeacherJudgeAttachmentStatusLiteral
    error_message: str | None = None
    created_at: str


class TeacherJudgeSessionAttachmentUploadResponse(BaseModel):
    attachment: TeacherJudgeSessionAttachmentPublic


class TeacherJudgeSessionScriptCreateRequest(BaseModel):
    """Create a session script only from the currently confirmed rubric revision."""

    analysis_revision: int | None = Field(default=None, ge=1)


class TeacherJudgeScriptCreateRequest(BaseModel):
    """Create a managed script artifact from the current rubric analysis."""

    name: str = Field(..., min_length=1, max_length=255)
    template_key: str = Field(default="linux", max_length=50)
    rubric_snapshot: TeacherJudgeRubricAnalysis
    source_file_id: uuid.UUID | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError(t("schemas.name_blank"))
        return name

    @field_validator("template_key")
    @classmethod
    def normalize_template_key(cls, value: str) -> str:
        return value.strip().lower() or "linux"


class TeacherJudgeScriptRegenerateRequest(BaseModel):
    """Regenerate a managed script artifact."""

    rubric_snapshot: TeacherJudgeRubricAnalysis | None = None


class TeacherJudgeScriptUpdateRequest(BaseModel):
    """Rename a managed script artifact."""

    name: str = Field(..., min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError(t("schemas.name_blank"))
        return name


class TeacherJudgeScriptArtifactPublic(BaseModel):
    id: str
    artifact_set_id: str | None = None
    target_node_key: str | None = None
    source_analysis_revision: int | None = None
    teaching_class_id: str
    session_id: str | None = None
    name: str
    template_key: str
    rubric_snapshot_json: dict[str, Any]
    source_file_id: str | None
    source_file_snapshot_json: dict[str, Any]
    script_language: TeacherJudgeScriptLanguageLiteral
    script_content: str
    source: TeacherJudgeScriptSourceLiteral
    version: int
    status: TeacherJudgeScriptStatusLiteral
    policy_check_result_json: dict[str, Any]
    ai_review_result_json: dict[str, Any]
    created_by: str | None
    approved_by: str | None
    created_at: str
    updated_at: str
    approved_at: str | None


class TeacherJudgeFilePublic(BaseModel):
    id: str
    teaching_class_id: str
    uploaded_by: str | None
    original_filename: str | None
    file_hash: str | None
    template_key: str
    source_type: TeacherJudgeFileSourceTypeLiteral = "uploaded"
    display_name: str
    environment_keys: list[str] = Field(default_factory=list)
    analysis_revision: int = 1
    analysis_json: dict[str, Any]
    status: TeacherJudgeFileStatusLiteral
    created_at: str
    updated_at: str


class TeacherJudgeFileAnalysisUpdateRequest(BaseModel):
    analysis: TeacherJudgeRubricAnalysis
    expected_revision: int | None = Field(default=None, ge=1)


class TeacherJudgeSessionForkRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("title")
    @classmethod
    def normalize_fork_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        title = value.strip()
        if not title:
            raise ValueError(t("schemas.title_blank"))
        return title


class TeacherJudgeScriptRunCreateRequest(BaseModel):
    """Create an execution run for an approved managed script."""

    target_scope: TeacherJudgeScriptRunTargetScopeLiteral = "manual"
    target_node_key: str | None = Field(default=None, max_length=80)
    target_vmids: list[int] = Field(default_factory=list)

    @field_validator("target_node_key")
    @classmethod
    def normalize_target_node_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("target_vmids")
    @classmethod
    def validate_target_vmids(cls, value: list[int]) -> list[int]:
        unique_vmids = list(dict.fromkeys(value))
        return unique_vmids

    @model_validator(mode="after")
    def validate_target_selector(self) -> TeacherJudgeScriptRunCreateRequest:
        if self.target_scope == "manual":
            if not self.target_vmids:
                raise ValueError(t("schemas.target_vmids_empty"))
            return self
        if self.target_scope == "all_students_on_node":
            if not self.target_node_key:
                raise ValueError(t("schemas.target_node_key_required"))
            if self.target_vmids:
                raise ValueError(t("schemas.target_vmids_not_allowed"))
            return self
        # Keep the pre-node-selector API usable while old callers migrate. The
        # service still resolves these scopes from the explicitly supplied VMIDs.
        if not self.target_node_key and not self.target_vmids:
            raise ValueError(t("schemas.target_node_key_required"))
        if self.target_node_key and self.target_vmids:
            raise ValueError(t("schemas.target_vmids_not_allowed"))
        return self


class TeacherJudgeScriptRunPublic(BaseModel):
    id: str
    run_batch_id: str | None = None
    teaching_class_id: str
    artifact_id: str
    target_scope: TeacherJudgeScriptRunTargetScopeLiteral
    target_snapshot_json: dict[str, Any]
    status: TeacherJudgeScriptRunStatusLiteral
    progress_json: dict[str, Any]
    result_summary_json: dict[str, Any]
    target_results_json: dict[str, Any]
    started_by: str | None
    started_at: str | None
    finished_at: str | None
    created_at: str
    updated_at: str


class TeacherJudgeScriptRunSummary(BaseModel):
    id: str
    run_batch_id: str | None = None
    teaching_class_id: str
    artifact_id: str
    status: TeacherJudgeScriptRunStatusLiteral
    progress_json: dict[str, Any]
    result_summary_json: dict[str, Any]
    started_at: str | None
    finished_at: str | None
    created_at: str
    updated_at: str


class TeacherJudgeScriptSetPublic(BaseModel):
    artifact_set_id: str
    teaching_class_id: str
    session_id: str | None = None
    source_file_id: str | None = None
    source_analysis_revision: int | None = None
    status: Literal["approved", "review_failed", "mixed"]
    children: list[TeacherJudgeScriptArtifactPublic]


class TeacherJudgeScriptSetRunRequest(BaseModel):
    target_scope: Literal["all_students_in_set"] = "all_students_in_set"


class TeacherJudgeRunBatchNodePublic(BaseModel):
    target_node_key: str
    display_label: str | None = None
    artifact_id: str
    run_id: str
    status: TeacherJudgeScriptRunStatusLiteral
    progress_json: dict[str, Any]
    result_summary_json: dict[str, Any]


class TeacherJudgeRunBatchPublic(BaseModel):
    run_batch_id: str
    teaching_class_id: str
    session_id: str | None = None
    status: Literal["pending", "running", "completed", "completed_with_failures", "failed"]
    summary: dict[str, int]
    nodes: list[TeacherJudgeRunBatchNodePublic]
    students: list[dict[str, Any]] = Field(default_factory=list)


class TeacherJudgeTargetReviewUpdate(BaseModel):
    """Teacher-owned decisions and optional feedback for one run target."""

    feedback: str = Field(default="", max_length=4000)
    decisions: dict[str, Literal["pass", "fail"]] = Field(default_factory=dict)

    @field_validator("feedback")
    @classmethod
    def normalize_feedback(cls, value: str) -> str:
        return value.strip()

    @field_validator("decisions")
    @classmethod
    def validate_decisions(
        cls, value: dict[str, Literal["pass", "fail"]]
    ) -> dict[str, Literal["pass", "fail"]]:
        if len(value) > 100:
            raise ValueError("A target review cannot contain more than 100 decisions")
        normalized: dict[str, Literal["pass", "fail"]] = {}
        for raw_check_id, decision in value.items():
            check_id = raw_check_id.strip()
            if not check_id or len(check_id) > 255:
                raise ValueError("Review check ids must contain 1 to 255 characters")
            normalized[check_id] = decision
        return normalized
