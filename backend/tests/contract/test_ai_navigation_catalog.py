"""The navigation catalogue must describe the router the frontend actually has.

Before this guard existed the catalogue still served paths like /applications and
/admin/domains, and the frontend carried a PATH_MAP translation table to patch
them up at runtime.  A stale entry is worse than a missing one: the assistant
confidently sends the user to a route that redirects them away.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.ai.navigation.catalog import all_routes
from app.ai.navigation.flows import all_flows

_APP_JSX = (
    Path(__file__).resolve().parents[3] / "frontend" / "src" / "App.jsx"
)
_PATH_ATTR = re.compile(r'path="([^"]+)"')


def _router_paths() -> set[str]:
    source = _APP_JSX.read_text(encoding="utf-8")
    paths = set()
    for raw in _PATH_ATTR.findall(source):
        # 帶參數與萬用路由無法直接導覽，導覽目錄本來就不該收錄。
        if ":" in raw or "*" in raw:
            continue
        paths.add(raw)
    return paths


def test_app_jsx_is_readable() -> None:
    assert _APP_JSX.exists(), f"找不到前端路由表：{_APP_JSX}"
    assert _router_paths(), "沒有從 App.jsx 解析到任何路由，正則可能要更新"


@pytest.mark.parametrize("route", all_routes(), ids=lambda route: route.path)
def test_every_catalog_path_exists_in_the_router(route) -> None:
    assert route.path in _router_paths(), (
        f"導覽目錄的 {route.path} 不在 App.jsx 的路由表裡"
    )


@pytest.mark.parametrize("flow", all_flows(), ids=lambda flow: flow.flow_id)
def test_every_flow_step_points_at_a_catalog_route(flow) -> None:
    catalog_paths = {route.path for route in all_routes()}
    for step in flow.steps:
        assert step.path in catalog_paths, (
            f"流程 {flow.flow_id} 的步驟「{step.title}」指向未登錄的 {step.path}"
        )


@pytest.mark.parametrize("flow", all_flows(), ids=lambda flow: flow.flow_id)
def test_flow_steps_are_reachable_by_everyone_allowed_into_the_flow(flow) -> None:
    """流程不能包含使用者打不開的頁面，否則走到一半就卡住。"""
    rank = {"all": 0, "staff": 1, "admin": 2}
    routes = {route.path: route for route in all_routes()}
    for step in flow.steps:
        step_access = routes[step.path].access
        assert rank[step_access] <= rank[flow.access], (
            f"流程 {flow.flow_id}（{flow.access}）的步驟「{step.title}」"
            f"需要 {step_access} 權限"
        )


def test_catalog_paths_are_unique() -> None:
    paths = [route.path for route in all_routes()]
    assert len(paths) == len(set(paths))


def test_flow_ids_are_unique() -> None:
    ids = [flow.flow_id for flow in all_flows()]
    assert len(ids) == len(set(ids))
