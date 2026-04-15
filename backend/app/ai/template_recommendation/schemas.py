from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


PersonaPreset = Literal[
    "student_individual",
    "student_team_project",
    "teaching_class_service",
]


PRESET_RESOURCE_BASELINES: dict[str, dict[str, dict[str, int]]] = {
    "student_individual": {
        "lxc": {"cpu": 1, "memory_mb": 1024, "disk_gb": 8},
        "vm": {"cpu": 2, "memory_mb": 2048, "disk_gb": 20},
    },
    "student_team_project": {
        "lxc": {"cpu": 2, "memory_mb": 2048, "disk_gb": 16},
        "vm": {"cpu": 2, "memory_mb": 4096, "disk_gb": 40},
    },
    "teaching_class_service": {
        "lxc": {"cpu": 4, "memory_mb": 8192, "disk_gb": 40},
        "vm": {"cpu": 4, "memory_mb": 8192, "disk_gb": 60},
    },
}


PRESET_DEFAULTS: dict[str, dict[str, Any]] = {
    "student_individual": {
        "role": "student",
        "course_context": "coursework",
        "sharing_scope": "personal",
        "budget_mode": "low-cost",
        "expected_users": 1,
        "experience_level": "beginner",
    },
    "student_team_project": {
        "role": "student",
        "course_context": "coursework",
        "sharing_scope": "shared",
        "budget_mode": "balanced",
        "expected_users": 5,
        "experience_level": "intermediate",
    },
    "teaching_class_service": {
        "role": "teacher",
        "course_context": "teaching",
        "sharing_scope": "shared",
        "budget_mode": "stable",
        "expected_users": 30,
        "experience_level": "intermediate",
    },
}


class DeviceNode(BaseModel):
    node: str
    maxcpu: int = Field(default=0)
    cpu_usage_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    maxmem_gb: float = Field(default=0.0, ge=0.0)
    mem_usage_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    gpu_count: int = Field(default=0, ge=0)


class ChatMessage(BaseModel):
    role: str = Field(..., description="Role of the message sender, usually 'user' or 'assistant'.")
    content: str = Field(..., description="Content of the message.")


class ChatResponse(BaseModel):
    reply: str = Field(..., description="AI text reply.")
    prompt_tokens: int = Field(default=0)
    completion_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)
    elapsed_seconds: float = Field(default=0.0)
    tokens_per_second: float = Field(default=0.0)


class ExtractedIntent(BaseModel):
    goal_summary: str = Field(..., description="Summary of the user's final goal.")
    role: str = Field(default="student")
    course_context: str = Field(default="coursework")
    budget_mode: str = Field(default="balanced")
    needs_public_web: bool = Field(default=False)
    needs_database: bool = Field(default=False)
    requires_gpu: bool = Field(default=False)
    needs_windows: bool = Field(default=False)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1, description="List of previous chat messages.")
    top_k: int = Field(default=5, ge=1, le=10)
    device_nodes: list[DeviceNode] = Field(default_factory=list)



class RecommendationRequest(BaseModel):
    goal: str = Field(..., min_length=3)
    preset: PersonaPreset | None = Field(default=None)
    role: str = Field(default="student")
    course_context: str = Field(default="coursework")
    sharing_scope: str = Field(default="personal")
    budget_mode: str = Field(default="balanced")
    preferred_type: str | None = Field(default=None)
    expected_users: int = Field(default=1, ge=1, le=100000)
    requires_gpu: bool = False
    needs_windows: bool = False
    needs_public_web: bool = False
    needs_persistent_storage: bool = True
    needs_database: bool = False
    experience_level: str = Field(default="beginner")
    top_k: int = Field(default=5, ge=1, le=10)
    device_nodes: list[DeviceNode] = Field(default_factory=list)
    resource_baseline: dict[str, dict[str, int]] = Field(default_factory=dict)
    clarification_answers: list[dict[str, str]] | None = Field(default=None)

    @model_validator(mode="before")
    @classmethod
    def _apply_preset_defaults(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        preset = data.get("preset")
        if not preset or preset not in PRESET_DEFAULTS:
            return data

        defaults = PRESET_DEFAULTS[preset]
        for key, value in defaults.items():
            if key not in data or data.get(key) in (None, ""):
                data[key] = value

        if not data.get("resource_baseline"):
            data["resource_baseline"] = PRESET_RESOURCE_BASELINES[preset]

        return data

    @model_validator(mode="after")
    def _infer_preset_when_missing(self) -> "RecommendationRequest":
        if self.preset is None:
            if self.role == "teacher" and self.course_context == "teaching":
                self.preset = "teaching_class_service"
            elif self.role == "student" and self.sharing_scope == "shared":
                self.preset = "student_team_project"
            else:
                self.preset = "student_individual"

        if not self.resource_baseline:
            self.resource_baseline = PRESET_RESOURCE_BASELINES[self.preset]

        return self

