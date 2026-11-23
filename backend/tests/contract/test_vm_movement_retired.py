"""Regression checks for the retired automatic VM movement feature."""

from app.api.main import api_router
from app.models import ProxmoxConfig, VMRequest
from app.schemas.jobs import JobKind
from app.schemas.proxmox_config import ProxmoxConfigPublic, ProxmoxConfigUpdate
from app.schemas.vm_request import VMRequestPublic
from app.services.scheduling import coordinator
from tests.utils.routes import registered_paths


def test_retired_routes_are_not_registered() -> None:
    paths = registered_paths(api_router.routes)
    assert not any(path.startswith("/migration-jobs") for path in paths)


def test_retired_work_is_not_a_background_job_kind() -> None:
    assert "migration" not in {kind.value for kind in JobKind}


def test_legacy_settings_are_not_part_of_public_api_or_model() -> None:
    legacy = {
        "migration_enabled",
        "migration_max_per_rebalance",
        "migration_min_interval_minutes",
        "migration_retry_limit",
        "migration_worker_concurrency",
        "migration_job_claim_timeout_seconds",
        "migration_retry_backoff_seconds",
        "migration_lxc_live_enabled",
    }
    assert legacy.isdisjoint(ProxmoxConfigPublic.model_fields)
    assert legacy.isdisjoint(ProxmoxConfigUpdate.model_fields)
    assert legacy.isdisjoint(ProxmoxConfig.model_fields)


def test_request_api_exposes_provisioning_instead_of_legacy_state() -> None:
    assert "provisioning_status" in VMRequestPublic.model_fields
    assert "provisioning_error" in VMRequestPublic.model_fields
    assert "migration_status" not in VMRequestPublic.model_fields
    assert "migration_error" not in VMRequestPublic.model_fields
    assert "provisioning_status" in VMRequest.model_fields


def test_scheduler_has_no_automatic_vm_movement_entrypoint() -> None:
    assert not hasattr(coordinator, "_rebalance_active_window")
    assert not hasattr(coordinator, "_process_pending_migration_jobs")
