"""規格調整申請 schemas"""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.spec_change_request import SpecChangeRequestStatus, SpecChangeType

# ===== Request Schemas =====


class SpecChangeRequestCreate(BaseModel):
    """建立規格調整申請"""

    vmid: int
    change_type: SpecChangeType
    reason: str = Field(min_length=10, description="調整原因至少10字")
    requested_cpu: int | None = Field(default=None, ge=1, le=32)
    requested_memory: int | None = Field(default=None, ge=512, le=65536)
    requested_disk: int | None = Field(default=None, ge=1, le=1000)


class SpecChangeRequestReview(BaseModel):
    """審核規格調整申請"""

    status: SpecChangeRequestStatus
    review_comment: str | None = None


# ===== Response Schemas =====


class SpecChangeRequestPublic(BaseModel):
    """公開的規格調整申請資訊"""

    id: uuid.UUID
    vmid: int
    user_id: uuid.UUID
    user_email: str | None = None
    user_full_name: str | None = None
    change_type: SpecChangeType
    reason: str
    current_cpu: int | None
    current_memory: int | None
    current_disk: int | None
    requested_cpu: int | None
    requested_memory: int | None
    requested_disk: int | None
    status: SpecChangeRequestStatus
    reviewer_id: uuid.UUID | None
    review_comment: str | None
    reviewed_at: datetime | None
    applied_at: datetime | None
    created_at: datetime


class SpecChangeRequestsPublic(BaseModel):
    """規格調整申請列表"""

    data: list[SpecChangeRequestPublic]
    count: int
