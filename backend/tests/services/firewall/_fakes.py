"""firewall_service 測試共用的假 PVE 防火牆端點：規則與選項的讀寫，並可注入指定操作的失敗。"""

from __future__ import annotations

from typing import Any

import pytest

from app.services.network import firewall_service as fw

# ─── 假 PVE 防火牆端點 ─────────────────────────────────────────────────────────


class _RuleAt:
    def __init__(self, firewall: FakeFirewall, pos: Any) -> None:
        self.firewall = firewall
        self.pos = pos

    def put(self, **kwargs: Any) -> None:
        if "put" in self.firewall.fail:
            raise RuntimeError("put boom")
        self.firewall.calls.append(("put", self.pos, kwargs))
        if self.firewall.on_put is not None:
            self.firewall.on_put(self.pos, kwargs)

    def delete(self) -> None:
        if "delete" in self.firewall.fail:
            raise RuntimeError("delete boom")
        self.firewall.calls.append(("delete", self.pos))


class _Rules:
    def __init__(self, firewall: FakeFirewall) -> None:
        self.firewall = firewall

    def __call__(self, pos: Any) -> _RuleAt:
        return _RuleAt(self.firewall, pos)

    def get(self) -> list[dict] | None:
        if "get" in self.firewall.fail:
            raise RuntimeError("get boom")
        return self.firewall.rules_data

    def post(self, **kwargs: Any) -> None:
        if "post" in self.firewall.fail or (
            self.firewall.fail_post_comment is not None
            and kwargs.get("comment") == self.firewall.fail_post_comment
        ):
            raise RuntimeError("post boom")
        self.firewall.calls.append(("post", kwargs))


class _Options:
    def __init__(self, firewall: FakeFirewall) -> None:
        self.firewall = firewall

    def get(self) -> dict:
        if "options_get" in self.firewall.fail:
            raise RuntimeError("options get boom")
        return self.firewall.options_data

    def put(self, **kwargs: Any) -> None:
        if "options_put" in self.firewall.fail:
            raise RuntimeError("options put boom")
        self.firewall.calls.append(("options_put", kwargs))


class FakeFirewall:
    def __init__(
        self,
        rules: list[dict] | None = None,
        options: dict | None = None,
        fail: tuple[str, ...] = (),
        fail_post_comment: str | None = None,
    ) -> None:
        self.rules_data = rules
        self.options_data = options if options is not None else {}
        self.fail = set(fail)
        self.fail_post_comment = fail_post_comment
        self.calls: list[tuple] = []
        self.on_put: Any = None
        self.rules = _Rules(self)
        self.options = _Options(self)


def _install_fw(
    monkeypatch: pytest.MonkeyPatch, firewall: FakeFirewall
) -> FakeFirewall:
    monkeypatch.setattr(fw, "_firewall_api", lambda node, vmid, rtype: firewall)
    return firewall
