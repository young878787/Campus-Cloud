from __future__ import annotations

from dataclasses import dataclass
import threading
import time


@dataclass
class _MetricsState:
    started_at_monotonic: float
    requests_total: int = 0
    requests_error_total: int = 0
    analysis_total: int = 0
    analyze_with_placement_total: int = 0
    proxmox_fetch_failures_total: int = 0
    backend_traffic_fetch_failures_total: int = 0
    avg_request_latency_ms: float = 0.0
    avg_analysis_latency_ms: float = 0.0


_lock = threading.Lock()
_state = _MetricsState(started_at_monotonic=time.monotonic())


def observe_http_request(*, duration_ms: float, success: bool) -> None:
    with _lock:
        _state.requests_total += 1
        if not success:
            _state.requests_error_total += 1
        _state.avg_request_latency_ms = _ema(_state.avg_request_latency_ms, duration_ms)


def observe_analysis(*, duration_ms: float, with_placement: bool) -> None:
    with _lock:
        _state.analysis_total += 1
        if with_placement:
            _state.analyze_with_placement_total += 1
        _state.avg_analysis_latency_ms = _ema(_state.avg_analysis_latency_ms, duration_ms)


def increment_proxmox_failure() -> None:
    with _lock:
        _state.proxmox_fetch_failures_total += 1


def increment_backend_traffic_failure() -> None:
    with _lock:
        _state.backend_traffic_fetch_failures_total += 1


def snapshot() -> dict:
    now = time.monotonic()
    with _lock:
        uptime_seconds = max(now - _state.started_at_monotonic, 0.0)
        return {
            "uptime_seconds": round(uptime_seconds, 2),
            "requests_total": _state.requests_total,
            "requests_error_total": _state.requests_error_total,
            "analysis_total": _state.analysis_total,
            "analyze_with_placement_total": _state.analyze_with_placement_total,
            "proxmox_fetch_failures_total": _state.proxmox_fetch_failures_total,
            "backend_traffic_fetch_failures_total": _state.backend_traffic_fetch_failures_total,
            "avg_request_latency_ms": round(_state.avg_request_latency_ms, 2),
            "avg_analysis_latency_ms": round(_state.avg_analysis_latency_ms, 2),
        }


def _ema(current: float, value: float, *, alpha: float = 0.2) -> float:
    if current <= 0:
        return max(value, 0.0)
    return (alpha * max(value, 0.0)) + ((1.0 - alpha) * current)
