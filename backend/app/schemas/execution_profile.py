"""Execution profile API 與 AI 白名單 DTO。"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ExecutionProfileContext(BaseModel):
    profile_key: str
    system_name: str
    system_version: str | None
    manual: str


class ExecutionProfileCreate(BaseModel):
    profile_key: str = Field(min_length=1, max_length=100)
    display_name: str = Field(min_length=1, max_length=150)
    system_name: str = Field(min_length=1, max_length=100)
    system_version: str | None = Field(default=None, max_length=50)
    manual: str = Field(max_length=2000)
    enabled: bool = True


class ExecutionProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=150)
    system_name: str | None = Field(default=None, min_length=1, max_length=100)
    system_version: str | None = Field(default=None, max_length=50)
    manual: str | None = Field(default=None, max_length=2000)
    enabled: bool | None = None


class ExecutionProfilePublic(ExecutionProfileCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ExecutionProfileCommandCreate(BaseModel):
    command_key: str = Field(min_length=1, max_length=100)
    command_label: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=50)
    command_template: str = Field(min_length=1)
    description: str
    risk_level: str = Field(default="read_only", max_length=30)
    requires_confirmation: bool = True
    enabled: bool = True


class ExecutionProfileCommandUpdate(BaseModel):
    command_label: str | None = Field(default=None, min_length=1, max_length=100)
    category: str | None = Field(default=None, min_length=1, max_length=50)
    command_template: str | None = Field(default=None, min_length=1)
    description: str | None = None
    risk_level: str | None = Field(default=None, max_length=30)
    requires_confirmation: bool | None = None
    enabled: bool | None = None


class ExecutionProfileCommandPublic(ExecutionProfileCommandCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    profile_id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class ResourceExecutionReconcileResult(BaseModel):
    scanned: int
    updated: int
    unresolved: int
    failed_vmids: list[int] = Field(default_factory=list)
