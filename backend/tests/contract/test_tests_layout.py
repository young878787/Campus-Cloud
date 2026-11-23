"""測試目錄規範檢查（P5）。

- 規則 1：tests/ 根目錄只放 ``__init__.py``、``conftest.py``；用到共用 ``db`` fixture 或標 ``integration`` marker（例如連真 Redis）的測試只能放在 ``tests/integration/``。
- 規則 2：測試檔名不得含 ``_coverage``、``_fixes`` 或日期；既有違規檔列在 ``_FROZEN_NAME_EXCEPTIONS``。

凍結清單只能減少不能增加：檔案改名、合併或刪除後，要同步從清單移除。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

TESTS_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = TESTS_ROOT.parent
_ROOT_ALLOWED = frozenset({"__init__.py", "conftest.py"})
_BAD_NAME = re.compile(r"_coverage|_fixes|_20[0-9][0-9]_")

# 既有違規檔，只能減少不能增加（P5 規則 2）
_FROZEN_NAME_EXCEPTIONS: frozenset[str] = frozenset(
    {
        "ai/teacher_judge/test_attachment_service_coverage.py",
        "ai/teacher_judge/test_automation_support_coverage.py",
        "ai/teacher_judge/test_check_plan_contract_coverage.py",
        "ai/teacher_judge/test_deterministic_compiler_coverage.py",
        "ai/teacher_judge/test_file_service_coverage.py",
        "ai/teacher_judge/test_machine_context_coverage.py",
        "ai/teacher_judge/test_schemas_coverage.py",
        "ai/teacher_judge/test_script_artifact_service_coverage.py",
        "ai/teacher_judge/test_script_executor_service_coverage.py",
        "ai/teacher_judge/test_script_policy_coverage.py",
        "ai/teacher_judge/test_script_quality_validator_coverage.py",
        "ai/teacher_judge/test_script_run_service_coverage.py",
        "ai/teacher_judge/test_session_route_fixes.py",
        "ai/teacher_judge/test_session_service_coverage.py",
        "ai/teacher_judge/test_target_ip_resolver_coverage.py",
        "ai/teacher_judge/test_teacher_judge_service_coverage.py",
        "ai/teacher_judge/test_teacher_judge_sessions_routes_coverage.py",
        "ai/teacher_judge/test_teacher_judge_small_modules_coverage.py",
        "ai/test_adherence_check_coverage.py",
        "ai/test_contextual_help_parts_coverage.py",
        "ai/test_contextual_help_service_coverage.py",
        "ai/test_monitoring_coverage.py",
        "ai/test_navigation_intake_coverage.py",
        "ai/test_navigation_service_coverage.py",
        "ai/test_pve_log_chat_coverage.py",
        "ai/test_pve_log_collector_coverage.py",
        "ai/test_pve_log_fixes.py",
        "ai/test_pve_log_guest_diagnostics_coverage.py",
        "ai/test_pve_log_history_coverage.py",
        "ai/test_pve_log_ssh_exec_coverage.py",
        "ai/test_role_contracts_coverage.py",
        "ai/test_system_config_coverage.py",
        "ai/test_template_recommendation_options_coverage.py",
        "ai/test_template_recommendation_service_coverage.py",
        "ai/test_utils_coverage.py",
        "ai/test_vllm_settings_coverage.py",
        "api/routes/test_ai_monitoring_routes_coverage.py",
        "api/routes/test_ai_routes_coverage.py",
        "api/routes/test_batch_provision_routes_coverage.py",
        "api/routes/test_cloudflare_routes_coverage.py",
        "api/routes/test_course_admin_routes_coverage.py",
        "api/routes/test_course_environment_fixes.py",
        "api/routes/test_firewall_routes_coverage.py",
        "api/routes/test_gateway_routes_coverage.py",
        "api/routes/test_ip_management_routes_coverage.py",
        "api/routes/test_platform_routes_coverage.py",
        "api/routes/test_proxmox_config_routes_coverage.py",
        "api/routes/test_resource_network_route_fixes.py",
        "api/routes/test_resource_routes_coverage.py",
        "api/routes/test_resource_settings_routes_coverage.py",
        "api/routes/test_reverse_proxy_routes_coverage.py",
        "api/routes/test_teaching_class_fixes.py",
        "api/routes/test_teaching_classes_coverage.py",
        "api/routes/test_teaching_routes_coverage.py",
        "api/routes/test_templates_routes_coverage.py",
        "api/test_api_deps_b05_coverage.py",
        "api/test_websocket_classroom_coverage.py",
        "api/test_websocket_course_progress_coverage.py",
        "api/test_websocket_jobs_coverage.py",
        "api/test_websocket_terminal_coverage.py",
        "api/test_websocket_utils_coverage.py",
        "api/test_websocket_vnc_coverage.py",
        "app_utils/test_sha512_crypt_coverage.py",
        "app_utils/test_utils_hostname_token_email_coverage.py",
        "core/test_core_coverage.py",
        "core/test_main_coverage.py",
        "domain/test_placement_domain_coverage.py",
        "domain/test_scheduling_runner_and_username_policy_coverage.py",
        "infrastructure/test_ai_infra_coverage.py",
        "infrastructure/test_background_tasks_coverage.py",
        "infrastructure/test_cloudflare_client_coverage.py",
        "infrastructure/test_ldap_client_coverage.py",
        "infrastructure/test_proxmox_client_coverage.py",
        "infrastructure/test_proxmox_guest_coverage.py",
        "infrastructure/test_proxmox_operations_coverage.py",
        "infrastructure/test_proxmox_router_coverage.py",
        "infrastructure/test_proxmox_settings_coverage.py",
        "infrastructure/test_proxmox_tls_coverage.py",
        "infrastructure/test_queue_coverage.py",
        "infrastructure/test_rate_limiter_coverage.py",
        "infrastructure/test_redis_client_coverage.py",
        "infrastructure/test_ssh_client_coverage.py",
        "infrastructure/test_token_blacklist_coverage.py",
        "infrastructure/test_vnc_coverage.py",
        "integration/api/routes/test_platform_route_fixes.py",
        "integration/services/test_ai_gateway_service_coverage.py",
        "integration/services/test_proxmox_fixes.py",
        "migrations/test_migration_versions_b05_coverage.py",
        "repositories/test_audit_log_repo_coverage.py",
        "repositories/test_batch_provision_repo_coverage.py",
        "repositories/test_cloudflare_config_repo_coverage.py",
        "repositories/test_governance_repo_coverage.py",
        "repositories/test_mining_repo_coverage.py",
        "repositories/test_nat_rule_repo_coverage.py",
        "repositories/test_proxmox_config_repo_coverage.py",
        "repositories/test_proxmox_connection_repo_coverage.py",
        "repositories/test_proxmox_node_repo_coverage.py",
        "repositories/test_proxmox_storage_repo_coverage.py",
        "repositories/test_push_repo_coverage.py",
        "repositories/test_repository_fixes.py",
        "repositories/test_resource_repo_coverage.py",
        "repositories/test_resource_share_repo_coverage.py",
        "repositories/test_reverse_proxy_repo_coverage.py",
        "repositories/test_singleton_configs_repo_coverage.py",
        "repositories/test_spec_change_request_repo_coverage.py",
        "repositories/test_task_record_repo_coverage.py",
        "repositories/test_vm_request_repo_coverage.py",
        "repositories/test_vm_template_repo_coverage.py",
        "repositories/test_wireguard_firewall_user_repo_coverage.py",
        "schemas/test_schema_fixes.py",
        "schemas/test_schema_validators_coverage.py",
        "scripts/test_cli_entrypoints_coverage.py",
        "services/course/test_ai_assignment_service_coverage.py",
        "services/course/test_course_service_coverage.py",
        "services/course/test_progress_service_coverage.py",
        "services/course/test_reminder_service_coverage.py",
        "services/course/test_weekly_task_service_coverage.py",
        "services/test_ai_metrics_coverage.py",
        "services/test_ai_relay_service_coverage.py",
        "services/test_alert_service_coverage.py",
        "services/test_audit_2026_09_fixes.py",
        "services/test_audit_service_coverage.py",
        "services/test_auth_service_coverage.py",
        "services/test_backup_service_coverage.py",
        "services/test_batch_provision_service_coverage.py",
        "services/test_broadcast_hub_coverage.py",
        "services/test_class_capacity_service_coverage.py",
        "services/test_class_lifecycle_service_coverage.py",
        "services/test_class_network_service_coverage.py",
        "services/test_class_provision_service_coverage.py",
        "services/test_class_status_service_coverage.py",
        "services/test_classroom_service_coverage.py",
        "services/test_clone_service_coverage.py",
        "services/test_cloudflare_service_coverage.py",
        "services/test_coordinator_coverage.py",
        "services/test_course_environment_service_coverage.py",
        "services/test_course_publication_service_coverage.py",
        "services/test_credentials_service_coverage.py",
        "services/test_deletion_service_coverage.py",
        "services/test_gateway_certificate_service_coverage.py",
        "services/test_gateway_install_service_coverage.py",
        "services/test_gateway_service_coverage.py",
        "services/test_gpu_service_coverage.py",
        "services/test_grafana_service_coverage.py",
        "services/test_guest_ssh_login_coverage.py",
        "services/test_heartbeat_service_coverage.py",
        "services/test_ip_management_service_coverage.py",
        "services/test_jobs_service_coverage.py",
        "services/test_ldap_auth_service_coverage.py",
        "services/test_lifecycle_service_coverage.py",
        "services/test_live_ip_coverage.py",
        "services/test_llm_gateway_misc_coverage.py",
        "services/test_mining_service_coverage.py",
        "services/test_monitoring_service_coverage.py",
        "services/test_nat_service_coverage.py",
        "services/test_network_fixes.py",
        "services/test_nginx_gateway_service_coverage.py",
        "services/test_nginx_runtime_service_coverage.py",
        "services/test_os_identity_service_coverage.py",
        "services/test_placement_service_coverage.py",
        "services/test_placement_support_coverage.py",
        "services/test_platform_entry_service_coverage.py",
        "services/test_preflight_service_coverage.py",
        "services/test_prometheus_sd_service_coverage.py",
        "services/test_provisioning_service_coverage.py",
        "services/test_proxmox_fixes.py",
        "services/test_publish_target_policy_coverage.py",
        "services/test_push_policy_coverage.py",
        "services/test_quick_practice_coverage.py",
        "services/test_quota_service_coverage.py",
        "services/test_recurrence_coverage.py",
        "services/test_recurrence_scheduler_coverage.py",
        "services/test_reset_service_coverage.py",
        "services/test_resource_access_coverage.py",
        "services/test_resource_jobs_fixes.py",
        "services/test_resource_kind_coverage.py",
        "services/test_resource_service_coverage.py",
        "services/test_resource_tasks_coverage.py",
        "services/test_reverse_proxy_service_coverage.py",
        "services/test_rubric_parser_coverage.py",
        "services/test_scheduling_fixes.py",
        "services/test_scheduling_leader_coverage.py",
        "services/test_scheduling_support_coverage.py",
        "services/test_settings_service_coverage.py",
        "services/test_setup_service_coverage.py",
        "services/test_sharing_service_coverage.py",
        "services/test_snapshot_cleanup_service_coverage.py",
        "services/test_snapshot_service_coverage.py",
        "services/test_spec_change_service_coverage.py",
        "services/test_system_health_service_coverage.py",
        "services/test_teaching_access_coverage.py",
        "services/test_template_fixes.py",
        "services/test_template_service_coverage.py",
        "services/test_template_tasks_and_files_coverage.py",
        "services/test_totp_service_coverage.py",
        "services/test_user_package_and_avatar_coverage.py",
        "services/test_user_service_coverage.py",
        "services/test_vm_request_availability_service_coverage.py",
        "services/test_vm_request_expiry_service_coverage.py",
        "services/test_vm_request_fixes.py",
        "services/test_vm_request_service_coverage.py",
        "services/test_vnc_session_manager_coverage.py",
        "services/test_web_push_service_coverage.py",
        "services/test_wireguard_service_coverage.py",
    }
)


def _name_violations() -> set[str]:
    """回傳 tests/ 下檔名違規的 test_*.py，路徑相對 tests/ 且以 ``/`` 分隔。"""
    return {
        path.relative_to(TESTS_ROOT).as_posix()
        for path in TESTS_ROOT.rglob("test_*.py")
        if "__pycache__" not in path.parts and _BAD_NAME.search(path.name)
    }


def test_tests_root_holds_only_package_and_conftest() -> None:
    stray = sorted(
        path.name for path in TESTS_ROOT.glob("*.py") if path.name not in _ROOT_ALLOWED
    )
    assert not stray, (
        f"tests/ 根目錄只允許 __init__.py、conftest.py，多出：{stray}；"
        "依 P5 規則 1 移到對應 app/ 結構的子目錄"
    )


def test_new_test_files_avoid_coverage_fixes_and_date_names() -> None:
    new = sorted(_name_violations() - _FROZEN_NAME_EXCEPTIONS)
    assert not new, (
        f"新增檔名違規：{new}；P5 規則 2：新檔不使用 _coverage／_fixes／日期命名，請依被測模組命名"
    )


def test_frozen_name_exceptions_only_shrink() -> None:
    stale = sorted(_FROZEN_NAME_EXCEPTIONS - _name_violations())
    assert not stale, (
        f"以下凍結項目已不存在或已不符合命名違規條件：{stale}；請從 _FROZEN_NAME_EXCEPTIONS 移除，清單只減不增"
    )


def test_shared_db_tests_live_under_integration() -> None:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(TESTS_ROOT),
        "--collect-only",
        "-q",
        "-p",
        "no:cacheprovider",
        "-p",
        "no:cov",
        "-p",
        "no:xdist",
        "-m",
        "integration and not performance",
        f"--ignore={TESTS_ROOT / 'integration'}",
        f"--ignore={TESTS_ROOT / 'performance'}",
    ]
    # 子行程只 --collect-only、不執行測試，所以不會再進入本檔，不會遞迴
    try:
        result = subprocess.run(
            cmd,
            cwd=BACKEND_ROOT,
            env=os.environ,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("收集非 integration 測試逾時（120 秒），無法確認 P5 規則 1")
    if result.returncode not in (0, 5):  # 5 = 沒收集到測試，正是通過狀態
        tail = "\n".join((result.stdout + result.stderr).splitlines()[-40:])
        pytest.fail(
            f"收集測試失敗（returncode={result.returncode}），無法確認 P5 規則 1：\n{tail}"
        )
    leaked = [line for line in result.stdout.splitlines() if "::" in line]
    assert not leaked, (
        "P5 規則 1：用到共用 db fixture 或標 integration marker（例如連真 Redis）的測試要放 tests/integration/，以下測試不在該目錄：\n"
        + "\n".join(leaked)
    )
