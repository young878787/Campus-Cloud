"""Desktop client download & device auth endpoints.

The desktop client authenticates via a "device auth" flow:
1. Client calls POST /auth/device-code  -> gets a device_code
2. Client opens browser to {frontend}/login?device_code={code}
3. User logs in on the web, frontend auto-calls POST /auth/approve
4. Client polls GET /auth/poll?code={code} -> gets access_token
"""

import logging
import secrets
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/desktop-client", tags=["desktop-client"])

_STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "downloads"

# ─── Device auth in-memory store ─────────────────────────────────────────────

_DEVICE_CODE_TTL = 300  # 5 minutes
_device_codes: dict[str, dict] = {}  # code -> {token, created_at}


def _cleanup_expired() -> None:
    """Remove expired device codes."""
    now = time.time()
    expired = [k for k, v in _device_codes.items() if now - v["created_at"] > _DEVICE_CODE_TTL]
    for k in expired:
        del _device_codes[k]


class DeviceCodeResponse(BaseModel):
    device_code: str
    login_url: str
    expires_in: int


class DeviceApproveRequest(BaseModel):
    device_code: str


class DevicePollResponse(BaseModel):
    status: str  # "pending" | "approved"
    access_token: str | None = None


# ─── Device auth endpoints ───────────────────────────────────────────────────


@router.post("/auth/device-code")
def create_device_code() -> DeviceCodeResponse:
    """Generate a new device code for desktop client login."""
    _cleanup_expired()
    code = secrets.token_urlsafe(32)
    _device_codes[code] = {"token": None, "created_at": time.time()}
    frontend_url = str(settings.FRONTEND_HOST).rstrip("/")
    login_url = f"{frontend_url}/login?device_code={code}"
    return DeviceCodeResponse(device_code=code, login_url=login_url, expires_in=_DEVICE_CODE_TTL)


@router.post("/auth/approve")
def approve_device_code(
    body: DeviceApproveRequest,
    current_user: CurrentUser,
    session: SessionDep,
) -> dict:
    """Approve a device code (called by the frontend after user logs in).

    The current user's access token is associated with the device code.
    We generate a fresh token for the desktop client using the same user identity.
    """
    from datetime import timedelta  # noqa: PLC0415

    from app.core.security import create_access_token  # noqa: PLC0415

    _cleanup_expired()
    entry = _device_codes.get(body.device_code)
    if entry is None:
        raise HTTPException(status_code=404, detail="Device code not found or expired")

    if time.time() - entry["created_at"] > _DEVICE_CODE_TTL:
        del _device_codes[body.device_code]
        raise HTTPException(status_code=410, detail="Device code expired")

    # Generate a long-lived access token for the desktop client (8 hours)
    token = create_access_token(
        subject=str(current_user.id),
        expires_delta=timedelta(hours=8),
    )
    entry["token"] = token
    return {"status": "approved"}


@router.get("/auth/poll")
def poll_device_code(code: str) -> DevicePollResponse:
    """Poll for device code approval (called by the desktop client)."""
    _cleanup_expired()
    entry = _device_codes.get(code)
    if entry is None:
        raise HTTPException(status_code=404, detail="Device code not found or expired")

    if entry["token"] is not None:
        token = entry["token"]
        # One-time use: delete after retrieval
        del _device_codes[code]
        return DevicePollResponse(status="approved", access_token=token)

    return DevicePollResponse(status="pending")


# ─── Download endpoint ───────────────────────────────────────────────────────


@router.get("/download")
def download_desktop_client(session: SessionDep, current_user: CurrentUser):
    """Return the desktop client zip (Electron portable build).

    If DESKTOP_CLIENT_DOWNLOAD_URL is set, redirects to that URL (e.g. a
    GitHub Releases asset). Otherwise serves a local file from static/downloads/.
    """
    if settings.DESKTOP_CLIENT_DOWNLOAD_URL:
        return RedirectResponse(settings.DESKTOP_CLIENT_DOWNLOAD_URL, status_code=302)

    zip_path = _STATIC_DIR / "campus-cloud-connect.zip"
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="Desktop client zip not found")

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename="campus-cloud-connect.zip",
    )
