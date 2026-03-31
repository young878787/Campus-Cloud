from __future__ import annotations

import asyncio
import calendar
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any
from zoneinfo import ZoneInfo

import httpx

from app.schemas import (
    ClusterUsageSummary,
    HistoricalProfile,
    GuestTypeUsageSummary,
    GuestUsageSummary,
    HourlyUsagePoint,
    NodeUsageSummary,
    ProxmoxMonthlyAnalyticsResponse,
)


TIMEFRAME = "month"
DEFAULT_TIMEOUT = 20.0
ROOT_DIR = Path(__file__).resolve().parents[2]
EWMA_ALPHA = 0.6
P95_QUANTILE = 0.95


class ProxmoxAnalyticsError(RuntimeError):
    pass


@dataclass
class ProxmoxAnalyticsSettings:
    host: str
    user: str
    password: str
    verify_ssl: bool
    timeout: float
    timezone: str
    iso_storage: str
    data_storage: str


@dataclass
class _WeightedValue:
    value: float
    weight: float


@dataclass
class _UsageSeries:
    hourly: list[HourlyUsagePoint]
    average_cpu_ratio: float | None
    average_memory_ratio: float | None
    average_disk_ratio: float | None
    trend_cpu_ratio: float | None
    trend_memory_ratio: float | None
    trend_disk_ratio: float | None
    peak_cpu_ratio: float | None
    peak_memory_ratio: float | None
    peak_disk_ratio: float | None
    average_loadavg_1: float | None = None


class _ProxmoxSession:
    def __init__(self, settings: ProxmoxAnalyticsSettings) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(
            base_url=f"https://{settings.host}:8006/api2/json",
            verify=settings.verify_ssl,
            timeout=settings.timeout,
        )
        self._cookies: dict[str, str] = {}
        self._headers: dict[str, str] = {}

    async def __aenter__(self) -> "_ProxmoxSession":
        response = await self._client.post(
            "/access/ticket",
            data={
                "username": self._settings.user,
                "password": self._settings.password,
            },
        )
        response.raise_for_status()
        data = response.json()["data"]
        self._cookies = {"PVEAuthCookie": data["ticket"]}
        csrf = data.get("CSRFPreventionToken")
        if csrf:
            self._headers = {"CSRFPreventionToken": csrf}
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._client.aclose()

    async def get(self, path: str, **params: Any) -> list[dict[str, Any]] | dict[str, Any]:
        response = await self._client.get(
            path,
            params=params or None,
            cookies=self._cookies,
            headers=self._headers,
        )
        response.raise_for_status()
        return response.json()["data"]


def load_settings() -> ProxmoxAnalyticsSettings:
    values = _read_env_file(ROOT_DIR / ".env")
    values.update(_read_env_file(ROOT_DIR / "pve_ resource_simulator" / ".env"))
    values.update(os.environ)

    host = values.get("PROXMOX_HOST", "").strip()
    user = values.get("PROXMOX_USER", "").strip()
    password = values.get("PROXMOX_PASSWORD", "")

    missing = [
        key
        for key, value in (
            ("PROXMOX_HOST", host),
            ("PROXMOX_USER", user),
            ("PROXMOX_PASSWORD", password),
        )
        if not value
    ]
    if missing:
        raise ProxmoxAnalyticsError(
            "Missing Proxmox settings: " + ", ".join(missing)
        )

    timezone_name = values.get("PVE_ANALYTICS_TIMEZONE", "") or _local_timezone_name()
    return ProxmoxAnalyticsSettings(
        host=host,
        user=user,
        password=password,
        verify_ssl=_parse_bool(values.get("PROXMOX_VERIFY_SSL", "true")),
        timeout=float(values.get("PROXMOX_API_TIMEOUT", DEFAULT_TIMEOUT)),
        timezone=timezone_name,
        iso_storage=values.get("PROXMOX_ISO_STORAGE", "ISO"),
        data_storage=values.get("PROXMOX_DATA_STORAGE", "local-lvm"),
    )


async def fetch_monthly_analytics() -> ProxmoxMonthlyAnalyticsResponse:
    settings = load_settings()
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)

    try:
        async with _ProxmoxSession(settings) as session:
            nodes_payload, resources_payload = await asyncio.gather(
                session.get("/nodes"),
                session.get("/cluster/resources", type="vm"),
            )

            nodes = [item.get("node") or item.get("name") for item in nodes_payload]
            nodes = [item for item in nodes if item]
            resources = [
                item
                for item in resources_payload
                if item.get("type") in {"qemu", "lxc"} and item.get("template") != 1
            ]

            node_status_tasks = {
                node: asyncio.create_task(session.get(f"/nodes/{node}/status"))
                for node in nodes
            }
            node_rrd_tasks = {
                node: asyncio.create_task(
                    session.get(f"/nodes/{node}/rrddata", timeframe=TIMEFRAME, cf="AVERAGE")
                )
                for node in nodes
            }
            guest_status_tasks = {
                _guest_key(resource): asyncio.create_task(
                    session.get(
                        f"/nodes/{resource['node']}/{resource['type']}/{resource['vmid']}/status/current"
                    )
                )
                for resource in resources
            }
            guest_rrd_tasks = {
                _guest_key(resource): asyncio.create_task(
                    session.get(
                        f"/nodes/{resource['node']}/{resource['type']}/{resource['vmid']}/rrddata",
                        timeframe=TIMEFRAME,
                        cf="AVERAGE",
                    )
                )
                for resource in resources
            }

            node_status_map, node_status_errors = await _await_task_map(node_status_tasks)
            node_rrd_map, node_rrd_errors = await _await_task_map(node_rrd_tasks)
            guest_status_map, guest_status_errors = await _await_task_map(guest_status_tasks)
            guest_rrd_map, guest_rrd_errors = await _await_task_map(guest_rrd_tasks)
    except httpx.HTTPError as exc:
        raise ProxmoxAnalyticsError(f"Failed to query Proxmox API: {exc}") from exc

    return build_monthly_analytics(
        host=settings.host,
        timezone_name=settings.timezone,
        now=now,
        nodes_payload=nodes_payload,
        resources_payload=resources,
        node_status_map=node_status_map,
        node_rrd_map=node_rrd_map,
        guest_status_map=guest_status_map,
        guest_rrd_map=guest_rrd_map,
        node_error_map=_merge_error_maps(node_status_errors, node_rrd_errors),
        guest_error_map=_merge_error_maps(guest_status_errors, guest_rrd_errors),
    )


def build_monthly_analytics(
    *,
    host: str,
    timezone_name: str,
    now: datetime,
    nodes_payload: list[dict[str, Any]],
    resources_payload: list[dict[str, Any]],
    node_status_map: dict[str, dict[str, Any]],
    node_rrd_map: dict[str, list[dict[str, Any]]],
    guest_status_map: dict[str, dict[str, Any]],
    guest_rrd_map: dict[str, list[dict[str, Any]]],
    node_error_map: dict[str, str] | None = None,
    guest_error_map: dict[str, str] | None = None,
) -> ProxmoxMonthlyAnalyticsResponse:
    tz = ZoneInfo(timezone_name)
    month_start, month_end = _month_window(now)
    node_error_map = node_error_map or {}
    guest_error_map = guest_error_map or {}
    node_payload_map = {
        str(item.get("node") or item.get("name")): item
        for item in nodes_payload
        if item.get("node") or item.get("name")
    }

    node_summaries: list[NodeUsageSummary] = []
    sorted_nodes = sorted(
        [item.get("node") or item.get("name") for item in nodes_payload if item.get("node") or item.get("name")]
    )
    for node in sorted_nodes:
        status = node_status_map.get(node, {})
        usage = _build_usage_series(
            node_rrd_map.get(node, []),
            tz=tz,
            month_start=month_start,
            month_end=month_end,
        )
        current_cpu, _ = _node_current_cpu(status)
        current_memory, _ = _node_current_memory(status)
        current_disk, _ = _node_current_disk(status)
        node_summaries.append(
            NodeUsageSummary(
                name=node,
                status=(
                    status.get("status")
                    or node_payload_map.get(node, {}).get("status")
                    or ("unreachable" if node in node_error_map else None)
                ),
                fetch_error=node_error_map.get(node),
                total_cpu_cores=_to_float((status.get("cpuinfo") or {}).get("cpus")),
                total_memory_gb=_bytes_to_gib((status.get("memory") or {}).get("total")),
                total_disk_gb=_bytes_to_gib((status.get("rootfs") or {}).get("total")),
                current_cpu_ratio=current_cpu,
                current_memory_ratio=current_memory,
                current_disk_ratio=current_disk,
                average_cpu_ratio=usage.average_cpu_ratio,
                average_memory_ratio=usage.average_memory_ratio,
                average_disk_ratio=usage.average_disk_ratio,
                trend_cpu_ratio=usage.trend_cpu_ratio,
                trend_memory_ratio=usage.trend_memory_ratio,
                trend_disk_ratio=usage.trend_disk_ratio,
                peak_cpu_ratio=usage.peak_cpu_ratio,
                peak_memory_ratio=usage.peak_memory_ratio,
                peak_disk_ratio=usage.peak_disk_ratio,
                current_loadavg=_normalize_loadavg(status.get("loadavg")),
                average_loadavg_1=usage.average_loadavg_1,
                hourly=usage.hourly,
            )
        )

    guest_summaries: list[GuestUsageSummary] = []
    for resource in sorted(resources_payload, key=lambda item: (item.get("node", ""), item.get("vmid", 0))):
        key = _guest_key(resource)
        status = guest_status_map.get(key, {})
        usage = _build_usage_series(
            guest_rrd_map.get(key, []),
            tz=tz,
            month_start=month_start,
            month_end=month_end,
        )
        current_cpu, _ = _guest_current_cpu(status)
        current_memory, _ = _guest_current_memory(status)
        current_disk, _ = _guest_current_disk(status)
        guest_summaries.append(
            GuestUsageSummary(
                vmid=int(resource["vmid"]),
                name=str(resource.get("name") or f"{resource['type']}-{resource['vmid']}"),
                resource_type=str(resource["type"]),
                node=str(resource["node"]),
                status=status.get("status") or resource.get("status") or (
                    "unreachable" if key in guest_error_map else None
                ),
                fetch_error=guest_error_map.get(key),
                configured_cpu_cores=_to_float(resource.get("maxcpu")),
                configured_memory_gb=_bytes_to_gib(resource.get("maxmem")),
                configured_disk_gb=_bytes_to_gib(resource.get("maxdisk")),
                current_cpu_ratio=current_cpu,
                current_memory_ratio=current_memory,
                current_disk_ratio=current_disk,
                average_cpu_ratio=usage.average_cpu_ratio,
                average_memory_ratio=usage.average_memory_ratio,
                average_disk_ratio=usage.average_disk_ratio,
                trend_cpu_ratio=usage.trend_cpu_ratio,
                trend_memory_ratio=usage.trend_memory_ratio,
                trend_disk_ratio=usage.trend_disk_ratio,
                peak_cpu_ratio=usage.peak_cpu_ratio,
                peak_memory_ratio=usage.peak_memory_ratio,
                peak_disk_ratio=usage.peak_disk_ratio,
                hourly=usage.hourly,
            )
        )

    cluster_usage = _build_cluster_usage(
        nodes=node_summaries,
        resources=resources_payload,
        node_status_map=node_status_map,
        node_rrd_map=node_rrd_map,
        tz=tz,
        month_start=month_start,
        month_end=month_end,
    )

    return ProxmoxMonthlyAnalyticsResponse(
        host=host,
        timezone=timezone_name,
        generated_at=now.isoformat(),
        month_label=now.strftime("%Y-%m"),
        cluster=cluster_usage,
        nodes=node_summaries,
        guests=sorted(
            guest_summaries,
            key=lambda item: (
                -(item.average_cpu_ratio or 0.0),
                -(item.average_memory_ratio or 0.0),
                item.node,
                item.vmid,
            ),
        ),
        guest_types=_build_guest_type_summaries(guest_summaries),
    )


def _build_cluster_usage(
    *,
    nodes: list[NodeUsageSummary],
    resources: list[dict[str, Any]],
    node_status_map: dict[str, dict[str, Any]],
    node_rrd_map: dict[str, list[dict[str, Any]]],
    tz: ZoneInfo,
    month_start: datetime,
    month_end: datetime,
) -> ClusterUsageSummary:
    current_cpu = _weighted_average(
        [
            _WeightedValue(value=value, weight=weight)
            for status in node_status_map.values()
            for value, weight in [_node_current_cpu(status)]
            if value is not None and weight > 0
        ]
    )
    current_memory = _weighted_average(
        [
            _WeightedValue(value=value, weight=weight)
            for status in node_status_map.values()
            for value, weight in [_node_current_memory(status)]
            if value is not None and weight > 0
        ]
    )
    current_disk = _weighted_average(
        [
            _WeightedValue(value=value, weight=weight)
            for status in node_status_map.values()
            for value, weight in [_node_current_disk(status)]
            if value is not None and weight > 0
        ]
    )

    usage = _build_combined_usage_series(
        list(node_rrd_map.values()),
        tz=tz,
        month_start=month_start,
        month_end=month_end,
    )

    return ClusterUsageSummary(
        node_count=len(nodes),
        guest_count=len(resources),
        current_cpu_ratio=current_cpu,
        current_memory_ratio=current_memory,
        current_disk_ratio=current_disk,
        average_cpu_ratio=usage.average_cpu_ratio,
        average_memory_ratio=usage.average_memory_ratio,
        average_disk_ratio=usage.average_disk_ratio,
        trend_cpu_ratio=usage.trend_cpu_ratio,
        trend_memory_ratio=usage.trend_memory_ratio,
        trend_disk_ratio=usage.trend_disk_ratio,
        peak_cpu_ratio=usage.peak_cpu_ratio,
        peak_memory_ratio=usage.peak_memory_ratio,
        peak_disk_ratio=usage.peak_disk_ratio,
        hourly=usage.hourly,
    )


def _build_usage_series(
    points: list[dict[str, Any]],
    *,
    tz: ZoneInfo,
    month_start: datetime,
    month_end: datetime,
) -> _UsageSeries:
    filtered = [
        point
        for point in points
        if _point_in_month(point, tz=tz, month_start=month_start, month_end=month_end)
    ]
    filtered.sort(key=lambda point: int(point.get("time") or 0))
    return _build_usage_series_from_points(filtered, tz=tz)


def _build_combined_usage_series(
    series_list: list[list[dict[str, Any]]],
    *,
    tz: ZoneInfo,
    month_start: datetime,
    month_end: datetime,
) -> _UsageSeries:
    filtered: list[dict[str, Any]] = []
    for points in series_list:
        for point in points:
            if not _point_in_month(point, tz=tz, month_start=month_start, month_end=month_end):
                continue
            filtered.append(point)
    filtered.sort(key=lambda point: int(point.get("time") or 0))
    return _build_usage_series_from_points(filtered, tz=tz)


def _build_usage_series_from_points(
    points: list[dict[str, Any]],
    *,
    tz: ZoneInfo,
) -> _UsageSeries:
    buckets: dict[int, dict[str, list[Any]]] = {
        hour: {"cpu": [], "memory": [], "disk": [], "loadavg_1": []}
        for hour in range(24)
    }
    timeline_buckets: dict[int, dict[str, list[_WeightedValue]]] = {}
    cpu_values: list[_WeightedValue] = []
    memory_values: list[_WeightedValue] = []
    disk_values: list[_WeightedValue] = []
    load_values: list[float] = []

    for point in points:
        timestamp = int(point["time"])
        hour = datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(tz).hour
        timeline_entry = timeline_buckets.setdefault(
            timestamp,
            {"cpu": [], "memory": [], "disk": []},
        )

        cpu_value = _cpu_ratio(point)
        if cpu_value is not None:
            buckets[hour]["cpu"].append(cpu_value)
            timeline_entry["cpu"].append(cpu_value)
            cpu_values.append(cpu_value)

        memory_value = _memory_ratio(point)
        if memory_value is not None:
            buckets[hour]["memory"].append(memory_value)
            timeline_entry["memory"].append(memory_value)
            memory_values.append(memory_value)

        disk_value = _disk_ratio(point)
        if disk_value is not None:
            buckets[hour]["disk"].append(disk_value)
            timeline_entry["disk"].append(disk_value)
            disk_values.append(disk_value)

        load_value = _loadavg_1(point)
        if load_value is not None:
            buckets[hour]["loadavg_1"].append(load_value)
            load_values.append(load_value)

    hourly = [
        HourlyUsagePoint(
            hour=hour,
            label=f"{hour:02d}:00",
            sample_count=max(
                len(buckets[hour]["cpu"]),
                len(buckets[hour]["memory"]),
                len(buckets[hour]["disk"]),
                len(buckets[hour]["loadavg_1"]),
            ),
            cpu_ratio=_weighted_average(buckets[hour]["cpu"]),
            memory_ratio=_weighted_average(buckets[hour]["memory"]),
            disk_ratio=_weighted_average(buckets[hour]["disk"]),
            peak_cpu_ratio=_weighted_percentile(buckets[hour]["cpu"], P95_QUANTILE),
            peak_memory_ratio=_weighted_percentile(buckets[hour]["memory"], P95_QUANTILE),
            peak_disk_ratio=_weighted_percentile(buckets[hour]["disk"], P95_QUANTILE),
            loadavg_1=_safe_mean(buckets[hour]["loadavg_1"]),
        )
        for hour in range(24)
    ]
    ordered_timestamps = sorted(timeline_buckets)
    trend_cpu_values = [
        _weighted_average(timeline_buckets[timestamp]["cpu"])
        for timestamp in ordered_timestamps
    ]
    trend_memory_values = [
        _weighted_average(timeline_buckets[timestamp]["memory"])
        for timestamp in ordered_timestamps
    ]
    trend_disk_values = [
        _weighted_average(timeline_buckets[timestamp]["disk"])
        for timestamp in ordered_timestamps
    ]
    return _UsageSeries(
        hourly=hourly,
        average_cpu_ratio=_weighted_average(cpu_values),
        average_memory_ratio=_weighted_average(memory_values),
        average_disk_ratio=_weighted_average(disk_values),
        trend_cpu_ratio=_safe_ewma(trend_cpu_values),
        trend_memory_ratio=_safe_ewma(trend_memory_values),
        trend_disk_ratio=_safe_ewma(trend_disk_values),
        peak_cpu_ratio=_weighted_percentile(cpu_values, P95_QUANTILE),
        peak_memory_ratio=_weighted_percentile(memory_values, P95_QUANTILE),
        peak_disk_ratio=_weighted_percentile(disk_values, P95_QUANTILE),
        average_loadavg_1=_safe_mean(load_values),
    )


def _point_in_month(
    point: dict[str, Any],
    *,
    tz: ZoneInfo,
    month_start: datetime,
    month_end: datetime,
) -> bool:
    timestamp = point.get("time")
    if timestamp is None:
        return False
    current = datetime.fromtimestamp(int(timestamp), tz=timezone.utc).astimezone(tz)
    return month_start <= current <= month_end


def _cpu_ratio(point: dict[str, Any]) -> _WeightedValue | None:
    ratio = _to_float(point.get("cpu"))
    if ratio is None:
        return None
    weight = _to_float(point.get("maxcpu")) or 1.0
    return _WeightedValue(value=ratio, weight=max(weight, 1.0))


def _memory_ratio(point: dict[str, Any]) -> _WeightedValue | None:
    used = _to_float(point.get("mem"))
    total = _to_float(point.get("maxmem"))
    if used is None or total is None or total <= 0:
        used = _to_float(point.get("memused"))
        total = _to_float(point.get("memtotal"))
    if used is None or total is None or total <= 0:
        return None
    return _WeightedValue(value=used / total, weight=total)


def _disk_ratio(point: dict[str, Any]) -> _WeightedValue | None:
    used = _to_float(point.get("disk"))
    total = _to_float(point.get("maxdisk"))
    if used is None or total is None or total <= 0:
        used = _to_float(point.get("rootused"))
        total = _to_float(point.get("roottotal"))
    if used is None or total is None or total <= 0:
        return None
    return _WeightedValue(value=used / total, weight=total)


def _loadavg_1(point: dict[str, Any]) -> float | None:
    for key in ("loadavg", "loadavg1"):
        value = point.get(key)
        if isinstance(value, list) and value:
            parsed = _to_float(value[0])
            if parsed is not None:
                return parsed
        parsed = _to_float(value)
        if parsed is not None:
            return parsed
    return None


def _node_current_cpu(status: dict[str, Any]) -> tuple[float | None, float]:
    value = _to_float(status.get("cpu"))
    cpuinfo = status.get("cpuinfo") or {}
    weight = _to_float(cpuinfo.get("cpus")) or _to_float(status.get("maxcpu")) or 1.0
    return value, weight


def _node_current_memory(status: dict[str, Any]) -> tuple[float | None, float]:
    memory = status.get("memory") or {}
    used = _to_float(memory.get("used"))
    total = _to_float(memory.get("total"))
    if used is None or total is None or total <= 0:
        return None, 0.0
    return used / total, total


def _node_current_disk(status: dict[str, Any]) -> tuple[float | None, float]:
    rootfs = status.get("rootfs") or {}
    used = _to_float(rootfs.get("used"))
    total = _to_float(rootfs.get("total"))
    if used is None or total is None or total <= 0:
        return None, 0.0
    return used / total, total


def _guest_current_cpu(status: dict[str, Any]) -> tuple[float | None, float]:
    value = _to_float(status.get("cpu"))
    weight = _to_float(status.get("cpus")) or _to_float(status.get("maxcpu")) or 1.0
    return value, weight


def _guest_current_memory(status: dict[str, Any]) -> tuple[float | None, float]:
    used = _to_float(status.get("mem"))
    total = _to_float(status.get("maxmem"))
    if used is None or total is None or total <= 0:
        return None, 0.0
    return used / total, total


def _guest_current_disk(status: dict[str, Any]) -> tuple[float | None, float]:
    used = _to_float(status.get("disk"))
    total = _to_float(status.get("maxdisk"))
    if used is None or total is None or total <= 0:
        return None, 0.0
    return used / total, total


def _normalize_loadavg(value: Any) -> list[float]:
    if not isinstance(value, list):
        return []
    normalized = [_to_float(item) for item in value[:3]]
    return [item for item in normalized if item is not None]


def _weighted_average(values: list[_WeightedValue]) -> float | None:
    if not values:
        return None
    total_weight = sum(item.weight for item in values)
    if total_weight <= 0:
        return None
    return sum(item.value * item.weight for item in values) / total_weight


def _weighted_percentile(
    values: list[_WeightedValue],
    percentile: float,
) -> float | None:
    if not values:
        return None
    normalized = sorted(
        (item for item in values if item.weight > 0),
        key=lambda item: item.value,
    )
    if not normalized:
        return None
    total_weight = sum(item.weight for item in normalized)
    if total_weight <= 0:
        return None
    target_weight = max(0.0, min(percentile, 1.0)) * total_weight
    cumulative_weight = 0.0
    for item in normalized:
        cumulative_weight += item.weight
        if cumulative_weight + 1e-12 >= target_weight:
            return item.value
    return normalized[-1].value


def _safe_ewma(
    values: list[float | None],
    *,
    alpha: float = EWMA_ALPHA,
) -> float | None:
    normalized = [value for value in values if value is not None]
    if not normalized:
        return None
    baseline = normalized[0]
    for value in normalized[1:]:
        baseline = (alpha * value) + ((1 - alpha) * baseline)
    return baseline


def _safe_mean(values: list[float | None]) -> float | None:
    normalized = [value for value in values if value is not None]
    if not normalized:
        return None
    return mean(normalized)


def _safe_max(values: list[float | None]) -> float | None:
    normalized = [value for value in values if value is not None]
    if not normalized:
        return None
    return max(normalized)


def _safe_percentile(
    values: list[float | None],
    percentile: float,
) -> float | None:
    normalized = sorted(value for value in values if value is not None)
    if not normalized:
        return None
    rank = max(1, math.ceil(percentile * len(normalized)))
    return normalized[min(rank, len(normalized)) - 1]


def _guest_key(resource: dict[str, Any]) -> str:
    return f"{resource['type']}:{resource['node']}:{resource['vmid']}"


def _month_window(now: datetime) -> tuple[datetime, datetime]:
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_day = calendar.monthrange(now.year, now.month)[1]
    end = now.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)
    return start, min(end, now)


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bytes_to_gib(value: Any) -> float | None:
    numeric = _to_float(value)
    if numeric is None:
        return None
    return numeric / (1024 ** 3)


def _parse_bool(value: Any) -> bool:
    return str(value).strip().lower() not in {"0", "false", "no", "off", ""}


def _local_timezone_name() -> str:
    current = datetime.now().astimezone().tzinfo
    if isinstance(current, ZoneInfo):
        return current.key
    return "UTC"


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values


def _build_guest_type_summaries(guests: list[GuestUsageSummary]) -> list[GuestTypeUsageSummary]:
    grouped: dict[tuple[float | None, float | None], list[GuestUsageSummary]] = {}
    for guest in guests:
        key = (
            _round_group_value(guest.configured_cpu_cores),
            _round_group_value(guest.configured_memory_gb),
        )
        grouped.setdefault(key, []).append(guest)

    results: list[GuestTypeUsageSummary] = []
    for (cpu, memory), items in sorted(
        grouped.items(),
        key=lambda item: (
            item[0][0] is None,
            item[0][0] or 0.0,
            item[0][1] is None,
            item[0][1] or 0.0,
        ),
    ):
        results.append(
            GuestTypeUsageSummary(
                type_label=_format_guest_type_label(cpu, memory),
                configured_cpu_cores=cpu,
                configured_memory_gb=memory,
                guest_count=len(items),
                current_cpu_ratio=_safe_mean([item.current_cpu_ratio for item in items]),
                current_memory_ratio=_safe_mean([item.current_memory_ratio for item in items]),
                current_disk_ratio=_safe_mean([item.current_disk_ratio for item in items]),
                average_cpu_ratio=_safe_mean([item.average_cpu_ratio for item in items]),
                average_memory_ratio=_safe_mean([item.average_memory_ratio for item in items]),
                average_disk_ratio=_safe_mean([item.average_disk_ratio for item in items]),
                trend_cpu_ratio=_safe_mean([item.trend_cpu_ratio for item in items]),
                trend_memory_ratio=_safe_mean([item.trend_memory_ratio for item in items]),
                trend_disk_ratio=_safe_mean([item.trend_disk_ratio for item in items]),
                peak_cpu_ratio=_safe_percentile(
                    [item.peak_cpu_ratio for item in items],
                    P95_QUANTILE,
                ),
                peak_memory_ratio=_safe_percentile(
                    [item.peak_memory_ratio for item in items],
                    P95_QUANTILE,
                ),
                peak_disk_ratio=_safe_percentile(
                    [item.peak_disk_ratio for item in items],
                    P95_QUANTILE,
                ),
                sample_names=[item.name for item in items[:4]],
                hourly=_merge_guest_hourly(items),
            )
        )
    return results


def build_historical_profiles(guest_types: list[GuestTypeUsageSummary]) -> list[HistoricalProfile]:
    return [
        HistoricalProfile(
            type_label=item.type_label,
            configured_cpu_cores=item.configured_cpu_cores,
            configured_memory_gb=item.configured_memory_gb,
            guest_count=item.guest_count,
            average_cpu_ratio=item.average_cpu_ratio,
            average_memory_ratio=item.average_memory_ratio,
            trend_cpu_ratio=item.trend_cpu_ratio,
            trend_memory_ratio=item.trend_memory_ratio,
            peak_cpu_ratio=item.peak_cpu_ratio,
            peak_memory_ratio=item.peak_memory_ratio,
            hourly=item.hourly,
        )
        for item in guest_types
    ]


def _merge_guest_hourly(items: list[GuestUsageSummary]) -> list[HourlyUsagePoint]:
    points_by_hour: dict[int, list[HourlyUsagePoint]] = {}
    for item in items:
        for point in item.hourly:
            points_by_hour.setdefault(point.hour, []).append(point)

    merged: list[HourlyUsagePoint] = []
    for hour in range(24):
        group = points_by_hour.get(hour, [])
        merged.append(
            HourlyUsagePoint(
                hour=hour,
                label=f"{hour:02d}:00",
                sample_count=sum(point.sample_count for point in group),
                cpu_ratio=_safe_mean([point.cpu_ratio for point in group]),
                memory_ratio=_safe_mean([point.memory_ratio for point in group]),
                disk_ratio=_safe_mean([point.disk_ratio for point in group]),
                peak_cpu_ratio=_safe_percentile(
                    [point.peak_cpu_ratio for point in group],
                    P95_QUANTILE,
                ),
                peak_memory_ratio=_safe_percentile(
                    [point.peak_memory_ratio for point in group],
                    P95_QUANTILE,
                ),
                peak_disk_ratio=_safe_percentile(
                    [point.peak_disk_ratio for point in group],
                    P95_QUANTILE,
                ),
                loadavg_1=None,
            )
        )
    return merged


def _round_group_value(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 2)


def _format_guest_type_label(cpu: float | None, memory: float | None) -> str:
    if cpu is None or memory is None:
        return "Unknown config"
    return f"{_format_number(cpu)} vCPU / {_format_number(memory)} GiB"


def _format_number(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:.1f}"


async def _await_task_map(
    tasks: dict[str, asyncio.Task],
) -> tuple[dict[str, Any], dict[str, str]]:
    results: dict[str, Any] = {}
    errors: dict[str, str] = {}
    for key, task in tasks.items():
        try:
            results[key] = await task
        except httpx.HTTPError as exc:
            errors[key] = _format_http_error(exc)
    return results, errors


def _merge_error_maps(*maps: dict[str, str]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for mapping in maps:
        merged.update(mapping)
    return merged


def _format_http_error(exc: httpx.HTTPError) -> str:
    response = getattr(exc, "response", None)
    if response is not None:
        return f"HTTP {response.status_code}: {response.reason_phrase}"
    request = getattr(exc, "request", None)
    if request is not None:
        return f"{exc.__class__.__name__} while requesting {request.url}"
    return str(exc)
