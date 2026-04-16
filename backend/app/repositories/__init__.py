from . import cloudflare_config, gateway_config, group, reverse_proxy
from .audit_log import (
    create_audit_log,
    get_audit_logs,
    get_audit_logs_by_user,
    get_audit_logs_by_vmid,
)
from .resource import (
    create_resource,
    delete_resource,
    get_all_resources,
    get_resource_by_vmid,
    get_resources_by_user,
    update_resource,
)
from .spec_change_request import (
    create_spec_change_request,
    get_all_spec_change_requests,
    get_spec_change_request_by_id,
    get_spec_change_requests_by_user,
    mark_spec_change_applied,
    update_spec_change_request_status,
)
from .user import (
    DUMMY_HASH,
    authenticate,
    create_user,
    get_user_by_email,
    update_user,
)
from .vm_migration_job import (
    cancel_pending_jobs_for_request,
    claim_jobs_for_requests,
    create_or_update_pending_job,
    delete_jobs_for_request,
    get_latest_job_for_request,
    get_open_job_for_request,
    list_pending_jobs_for_requests,
    update_job_status,
)
from .vm_request import (
    create_vm_request,
    get_all_vm_requests,
    get_vm_request_by_id,
    get_vm_requests_by_user,
    update_vm_request_status,
)
