from __future__ import annotations

from typing import Any

from app.infrastructure.traefik import TraefikGatewayClient
from app.schemas.reverse_proxy import (
    ReverseProxyRuntimeSection,
    ReverseProxyRuntimeSnapshot,
)


def _as_mapping(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        return payload
    return None


def get_runtime_snapshot(*, session: object) -> ReverseProxyRuntimeSnapshot:
    with TraefikGatewayClient(session) as client:
        return ReverseProxyRuntimeSnapshot(
            version=_as_mapping(client.fetch_json("/api/version")),
            overview=_as_mapping(client.fetch_json("/api/overview")),
            entrypoints=client.fetch_collection("/api/entrypoints"),
            http=ReverseProxyRuntimeSection(
                routers=client.fetch_collection("/api/http/routers"),
                services=client.fetch_collection("/api/http/services"),
                middlewares=client.fetch_collection("/api/http/middlewares"),
            ),
            tcp=ReverseProxyRuntimeSection(
                routers=client.fetch_collection("/api/tcp/routers"),
                services=client.fetch_collection("/api/tcp/services"),
                middlewares=client.fetch_collection("/api/tcp/middlewares"),
            ),
            udp=ReverseProxyRuntimeSection(
                routers=client.fetch_collection("/api/udp/routers"),
                services=client.fetch_collection("/api/udp/services"),
                middlewares=[],
            ),
        )
