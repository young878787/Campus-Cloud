"""Deletion request API schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.deletion_request import DeletionRequestStatus


class DeletionRequestPublic(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    vmid: int
    name: str | None = None
    node: str | None = None
    resource_type: str | None = None
    purge: bool
    force: bool
    status: DeletionRequestStatus
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    user_email: str | None = None
    user_full_name: str | None = None


class DeletionRequestsPublic(BaseModel):
    data: list[DeletionRequestPublic]
    count: int


class DeletionRequestCreated(BaseModel):
    """Response when accepting a delete request (HTTP 202)."""

    id: uuid.UUID
    vmid: int
    status: DeletionRequestStatus
    message: str = Field(default="Deletion request queued")
