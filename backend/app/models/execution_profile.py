"""已確認的機器執行環境與受管指令。"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlmodel import Column, Field, SQLModel

from .base import get_datetime_utc


class ExecutionProfile(SQLModel, table=True):
    __tablename__ = "execution_profiles"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    profile_key: str = Field(max_length=100, unique=True, index=True)
    display_name: str = Field(max_length=150)
    system_name: str = Field(max_length=100)
    system_version: str | None = Field(default=None, max_length=50)
    manual: str = Field(sa_type=sa.Text())
    enabled: bool = Field(default=True, index=True)
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=sa.DateTime(timezone=True),
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=sa.DateTime(timezone=True),
    )


class ExecutionProfileCommand(SQLModel, table=True):
    __tablename__ = "execution_profile_commands"
    __table_args__ = (
        sa.UniqueConstraint(
            "profile_id",
            "command_key",
            name="uq_execution_profile_command_key",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    profile_id: uuid.UUID = Field(
        sa_column=Column(
            sa.Uuid,
            sa.ForeignKey("execution_profiles.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    command_key: str = Field(max_length=100)
    command_label: str = Field(max_length=100)
    category: str = Field(max_length=50)
    command_template: str = Field(sa_type=sa.Text())
    description: str = Field(sa_type=sa.Text())
    risk_level: str = Field(default="read_only", max_length=30)
    requires_confirmation: bool = Field(default=True)
    enabled: bool = Field(default=True, index=True)
    created_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=sa.DateTime(timezone=True),
    )
    updated_at: datetime = Field(
        default_factory=get_datetime_utc,
        sa_type=sa.DateTime(timezone=True),
    )


__all__ = ["ExecutionProfile", "ExecutionProfileCommand"]
