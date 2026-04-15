from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ReverseProxyRuleCreate(BaseModel):
    vmid: int = Field(gt=0)
    zone_id: str = Field(min_length=1, max_length=64)
    hostname_prefix: str = Field(default="", max_length=190)
    internal_port: int = Field(ge=1, le=65535)
    enable_https: bool = True


class ReverseProxyRuleUpdate(ReverseProxyRuleCreate):
    pass


class ReverseProxyZoneOption(BaseModel):
    id: str
    name: str


class ReverseProxySetupContext(BaseModel):
    enabled: bool
    gateway_ready: bool
    cloudflare_ready: bool
    reasons: list[str] = Field(default_factory=list)
    zones: list[ReverseProxyZoneOption] = Field(default_factory=list)
    default_dns_target_type: str | None = None
    default_dns_target_value: str | None = None


class ReverseProxyRuntimeSection(BaseModel):
    routers: list[dict[str, Any]] = Field(default_factory=list)
    services: list[dict[str, Any]] = Field(default_factory=list)
    middlewares: list[dict[str, Any]] = Field(default_factory=list)


class ReverseProxyRuntimeSnapshot(BaseModel):
    runtime_error: str | None = None
    version: dict[str, Any] | None = None
    overview: dict[str, Any] | None = None
    entrypoints: list[dict[str, Any]] = Field(default_factory=list)
    http: ReverseProxyRuntimeSection = Field(default_factory=ReverseProxyRuntimeSection)
    tcp: ReverseProxyRuntimeSection = Field(default_factory=ReverseProxyRuntimeSection)
    udp: ReverseProxyRuntimeSection = Field(default_factory=ReverseProxyRuntimeSection)


__all__ = [
    "ReverseProxyRuleCreate",
    "ReverseProxyRuleUpdate",
    "ReverseProxyZoneOption",
    "ReverseProxySetupContext",
    "ReverseProxyRuntimeSection",
    "ReverseProxyRuntimeSnapshot",
]
