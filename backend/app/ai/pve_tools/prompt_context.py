"""Compact prompt catalog generated from the resolved registry profile."""

from app.ai.pve_tools.schemas import ResolvedProfile


def render_check_catalog(profile: ResolvedProfile) -> str:
    if not profile.checks:
        return (
            "目前模板沒有已註冊的 guest check；確有必要進入 guest 時，"
            "只能使用需要人工確認的 ssh_exec。"
        )
    rows = "\n".join(
        f"- {check.key}：{check.description}" for check in profile.checks
    )
    return (
        "可用 guest checks：\n"
        f"{rows}\n\n"
        "優先使用 run_guest_check；只有 catalog 沒有適合項目時，"
        "才使用需要人工確認的 ssh_exec。"
    )
