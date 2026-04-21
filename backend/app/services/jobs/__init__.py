"""統一 Jobs 服務模組。

聚合多個來源的「需要等待的任務」，正規化為單一介面提供 API/WebSocket 使用。
"""

from .jobs_service import (
    JobAccessDeniedError,
    JobNotFoundError,
    get_job_detail,
    list_jobs,
    list_recent_for_user,
)

__all__ = [
    "JobAccessDeniedError",
    "JobNotFoundError",
    "get_job_detail",
    "list_jobs",
    "list_recent_for_user",
]
