from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from app.core.config import settings
from app.schemas import BackendTrafficSnapshot


def fetch_backend_traffic_snapshot() -> BackendTrafficSnapshot | None:
    if not settings.backend_api_base_url or not settings.backend_api_token:
        return None

    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=settings.backend_traffic_window_minutes)
    headers = {"Authorization": f"Bearer {settings.backend_api_token}"}
    url = (
        f"{settings.backend_api_base_url.rstrip('/')}/api/v1/vm-requests"
        f"?skip=0&limit={settings.backend_traffic_sample_limit}"
    )

    with httpx.Client(timeout=settings.backend_api_timeout) as client:
        response = client.get(url, headers=headers)
        response.raise_for_status()
        payload = response.json()

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return None

    sampled_rows = 0
    submitted = 0
    pending = 0
    approved = 0
    requested_cpu = 0
    requested_memory_mb = 0
    requested_disk_gb = 0

    for item in data:
        if not isinstance(item, dict):
            continue

        sampled_rows += 1
        status = str(item.get("status") or "").lower()
        created_at = _parse_iso_datetime(item.get("created_at"))
        if created_at is not None and created_at >= window_start:
            submitted += 1

        if status == "pending":
            pending += 1
        elif status == "approved":
            approved += 1

        requested_cpu += _safe_int(item.get("cores"))
        requested_memory_mb += _safe_int(item.get("memory"))
        requested_disk_gb += _safe_int(item.get("disk_size")) or _safe_int(
            item.get("rootfs_size")
        )

    return BackendTrafficSnapshot(
        source="backend_vm_requests",
        sampled_at=now,
        sample_size=sampled_rows,
        window_minutes=settings.backend_traffic_window_minutes,
        submitted_in_window=submitted,
        pending_total=pending,
        approved_total=approved,
        requested_cpu_cores_total=requested_cpu,
        requested_memory_mb_total=requested_memory_mb,
        requested_disk_gb_total=requested_disk_gb,
    )


def _parse_iso_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _safe_int(value: object) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0
