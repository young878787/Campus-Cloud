"""服務模板腳本部署 schemas"""

from datetime import date

from pydantic import BaseModel, Field


class ScriptDeployRequest(BaseModel):
    """服務模板無人值守部署請求"""

    template_slug: str = Field(..., description="模板 slug（如 docker）")
    script_path: str = Field(..., description="腳本路徑（如 ct/docker.sh）")
    hostname: str = Field(
        ..., pattern=r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", max_length=63
    )
    password: str = Field(..., min_length=5, max_length=128)
    cpu: int = Field(default=2, ge=1, le=16)
    ram: int = Field(default=2048, ge=256, le=65536)
    disk: int = Field(default=4, ge=1, le=500)
    unprivileged: bool = True
    ssh: bool = False
    environment_type: str = "服務模板"
    os_info: str | None = None
    expiry_date: date | None = None


class ScriptDeployResponse(BaseModel):
    """部署任務建立回應"""

    task_id: str
    message: str


class ScriptDeployStatus(BaseModel):
    """部署任務狀態"""

    task_id: str
    status: str  # "running", "completed", "failed"
    progress: str | None = None
    vmid: int | None = None
    message: str | None = None
    error: str | None = None
    output: str | None = None
