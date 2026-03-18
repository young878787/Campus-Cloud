# PVE Placement Advisor

Standalone FastAPI service for PVE resource placement planning.

This service is focused on:

- reading current PVE node and guest usage from Proxmox
- keeping basic node visibility
- accepting a VM/LXC request shape similar to the backend form
- deciding which node should host identical new instances based on CPU, memory, disk headroom, guest density, and estimated user pressure
- explaining the allocation reason through the recommendations output

## Main Behavior

- `GET /api/v1/analyze`
  returns current cluster summary, node capacities, and recommendations
- `POST /api/v1/placement/recommend`
  accepts workload specs and returns a placement plan
- `GET /api/v1/sources/preview`
  previews raw node, resource, token, and GPU sources

## Placement Inputs

The placement API accepts:

- `machine_name`
- `resource_type`
- `cores`
- `memory_mb`
- `disk_gb`
- `instance_count`
- `estimated_users_per_instance`

The current planner uses safe headroom, not raw full capacity:

- CPU safe headroom
- memory safe headroom
- disk safe headroom
- guest density guardrail
- user-pressure-adjusted CPU and memory planning

`PLACEMENT_HEADROOM_RATIO` reserves extra capacity on every node so the planner does not allocate to the absolute limit.

If `estimated_users_per_instance` is provided, the planner derives a safer effective CPU and memory requirement from:

- `SAFE_USERS_PER_CPU`
- `SAFE_USERS_PER_GIB`

This means the placement decision can become more conservative than the raw form values when the expected concurrent user load is high.

## Data Sources

### 1. Proxmox nodes and guests

The service reads:

- node CPU usage and total cores
- node memory usage and total memory
- node disk usage and total disk
- node uptime
- VM/LXC CPU, memory, disk, and running status

### 2. Optional snapshots

The service still supports env-based fallback snapshots:

- `NODES_SNAPSHOT_JSON`
- `TOKEN_USAGE_SNAPSHOT_JSON`
- `GPU_METRICS_SNAPSHOT_JSON`

Token and GPU snapshots are kept as optional source preview data, but the main planner is now node placement focused.

## Quick Start

```bash
cd ai-pve-placement-advisor
copy .env.example .env
pip install -r requirements.txt
python main.py
```

Default address:

```text
http://localhost:8011
```

Docs:

```text
http://localhost:8011/docs
```

## UI

`static/index.html` now includes:

- a placement form
- cluster summary
- node capacity cards
- recommendation reasons
- user-pressure-aware placement explanation

## Rename

This service was renamed from `ai-log-analytics` to `ai-pve-placement-advisor` because the primary job is now PVE placement guidance rather than generic log analytics.
