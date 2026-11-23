from datetime import UTC, datetime, timedelta

from app.ai.template_recommendation.recommendation_service import normalize_ai_result
from app.ai.template_recommendation.schemas import (
    RecommendationFormContext,
    RecommendationRequest,
)


def test_form_context_accepts_complete_prefill_and_schedule_options() -> None:
    start = datetime(2026, 7, 20, 10, tzinfo=UTC)
    context = RecommendationFormContext(
        resource_type="vm",
        mode="scheduled",
        hostname="ai-lab",
        reason="課程模型推論",
        vm_template_id=9000,
        username="student",
        cores=4,
        memory_mb=8192,
        disk_gb=40,
        storage="local-lvm",
        selected_gpu_mapping_id="gpu-a",
        schedule_options=[
            {
                "start_at": start,
                "end_at": start + timedelta(hours=1),
                "status": "available",
                "recommended_nodes": ["pve-gpu-01"],
            }
        ],
    )

    assert context.hostname == "ai-lab"
    assert context.memory_mb == 8192
    assert context.schedule_options[0].recommended_nodes == ["pve-gpu-01"]


def test_normalizer_selects_only_available_gpu_and_valid_schedule() -> None:
    start = datetime(2026, 7, 20, 10, tzinfo=UTC)
    end = start + timedelta(hours=4)
    request = RecommendationRequest(
        goal="需要 GPU 執行模型推論",
        requires_gpu=True,
        form_context=RecommendationFormContext(
            resource_type="vm",
            mode="scheduled",
            schedule_options=[{"start_at": start, "end_at": end}],
        ),
    )
    result = normalize_ai_result(
        {
            "form_prefill": {
                "resource_type": "vm",
                "mode": "scheduled",
                "gpu_mapping_id": "gpu-full",
                "start_at": start.isoformat(),
                "end_at": end.isoformat(),
                "cores": 4,
                "memory_mb": 8192,
                "disk_gb": 40,
            }
        },
        request,
        [],
        resource_options={
            "lxc_os_images": [],
            "vm_operating_systems": [],
            "gpu_options": [
                {"mapping_id": "gpu-full", "available_count": 0, "total_vram_mb": 24576},
                {"mapping_id": "gpu-free", "available_count": 1, "total_vram_mb": 16384},
            ],
        },
    )

    prefill = result["final_plan"]["form_prefill"]
    assert prefill["gpu_mapping_id"] == "gpu-free"
    assert prefill["start_at"] == start.isoformat()
    assert prefill["end_at"] == end.isoformat()
    assert prefill["storage"] == "local-lvm"


N8N_CATALOG = [
    {
        "template_id": 9100,
        "name": "n8n 自動化流程",
        "description": "已安裝 n8n 與 PostgreSQL，開機即可使用",
        "resource_type": "lxc",
        "cores": 2,
        "memory_mb": 4096,
        "disk_gb": 16,
    },
    {
        "template_id": 9200,
        "name": "Jupyter 資料分析",
        "description": "已安裝 JupyterLab",
        "resource_type": "qemu",
        "cores": 4,
        "memory_mb": 8192,
        "disk_gb": 40,
    },
]


def _plan(prefill: dict) -> dict:
    return normalize_ai_result(
        {"form_prefill": prefill},
        RecommendationRequest(goal="想要一台跑 n8n 的機器"),
        [],
        resource_options={
            "lxc_os_images": [{"value": "local:vztmpl/debian-12.tar.zst"}],
            "vm_operating_systems": [{"template_id": 8000, "label": "Ubuntu 22.04"}],
            "application_templates": N8N_CATALOG,
            "gpu_options": [],
        },
    )["final_plan"]["form_prefill"]


def test_planner_may_clone_a_container_application_template() -> None:
    prefill = _plan(
        {"resource_type": "lxc", "lxc_template_id": 9100, "cores": 2, "memory_mb": 4096}
    )

    assert prefill["lxc_template_id"] == 9100
    # 走克隆路徑時不能同時帶基礎映像，否則申請表單會兩邊都填
    assert prefill["lxc_os_image"] == ""


def test_an_unknown_template_id_falls_back_to_a_base_image() -> None:
    prefill = _plan({"resource_type": "lxc", "lxc_template_id": 4242})

    assert prefill["lxc_template_id"] == 0
    assert prefill["lxc_os_image"] == "local:vztmpl/debian-12.tar.zst"


def test_a_container_template_cannot_be_used_as_a_vm_source() -> None:
    prefill = _plan({"resource_type": "vm", "vm_template_id": 9100})

    # 9100 是容器範本，不在 VM 候選內，只能退回可用的 VM 來源
    assert prefill["vm_template_id"] in {8000, 9200}


def test_a_vm_application_template_stays_selectable() -> None:
    prefill = _plan({"resource_type": "vm", "vm_template_id": 9200})

    assert prefill["vm_template_id"] == 9200
