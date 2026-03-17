# AI Log Analytics

Standalone layered backend for AI log analysis and resource optimization.

Current MVP behavior:

- directly reads node and VM/LXC metrics from Proxmox
- directly reads audit logs from PostgreSQL
- accepts optional token usage and GPU metric snapshots from `.env`
- aggregates raw signals into features and events with a configurable stair coefficient
- produces a rule-based summary and optimization suggestions
- supports AI explanation and chat endpoints backed by vLLM, with rule-based fallback
- includes a built-in dashboard and chat box in `static/index.html`

This service no longer depends on:

- `USE_BACKEND_API`
- `BACKEND_BASE_URL`
- `BACKEND_SERVICE_TOKEN`

The required backend capabilities have been migrated into this service:

- Proxmox node listing
- Proxmox VM/LXC resource listing
- PostgreSQL audit-log query
- local aggregation and event generation

## Structure

- `main.py`: compatibility entrypoint
- `app/main.py`: FastAPI app
- `app/core/config.py`: environment-based settings
- `app/api/routes/analytics.py`: analysis API
- `app/api/routes/explain.py`: AI explanation and chat API
- `app/api/routes/sources.py`: source preview API
- `app/services/proxmox_source_service.py`: Proxmox source adapter
- `app/services/audit_source_service.py`: audit-log source adapter
- `app/services/ai_explainer_service.py`: AI explanation and fallback logic
- `app/services/snapshot_source_service.py`: snapshot/env source adapter
- `app/services/aggregation_service.py`: aggregation, feature, event, recommendation logic
- `app/services/analytics_service.py`: orchestration layer
- `app/schemas/`: request and response schemas

## Quick Start

```bash
cd ai-log-analytics
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

Main endpoints:

- `GET /api/v1/analyze`
- `POST /api/v1/explain`
- `POST /api/v1/chat`
- `GET /api/v1/sources/preview`

## Data Sources

### 1. Proxmox node and resource metrics

The service reads:

- node CPU usage ratio
- node total CPU cores
- node memory usage and total memory
- node uptime
- VM/LXC CPU usage ratio
- VM/LXC memory usage and total memory
- VM/LXC disk usage and total disk
- VM/LXC running status

These are used as the main operational metrics layer.

### 2. PostgreSQL audit logs

The service reads recent records from `audit_logs`, including:

- `action`
- `details`
- `vmid`
- `user_id`
- `user_email`
- `created_at`

This is the main operation-log layer. It gives context about who changed what and when.

### 3. Optional token usage snapshots

If you provide `TOKEN_USAGE_SNAPSHOT_JSON`, the service will analyze:

- request count
- prompt tokens
- completion tokens
- total tokens
- token growth ratio

This is currently snapshot-driven, not auto-ingested from vLLM.

### 4. Optional GPU metric snapshots

If you provide `GPU_METRICS_SNAPSHOT_JSON`, the service will analyze:

- GPU count
- average GPU utilization
- average GPU memory ratio

This is also snapshot-driven in the current MVP.

## What Is Analyzed

The current MVP analyzes these categories:

### Resource pressure

- cluster average CPU pressure
- cluster average memory pressure
- VM/LXC memory saturation risk
- available CPU capacity

### Operation context

- recent audit-log activity count
- recent action records tied to VMID and user
- whether audit-log data is available at all

### AI / LLM usage context

- total token volume
- token growth ratio
- request volume

### GPU usage context

- visible GPU capacity
- low-utilization GPU waste signals

## Current Event Types

The aggregation layer currently emits:

- `high_cpu`
- `high_memory`
- `oom_risk`
- `token_spike`
- `gpu_idle_waste`
- `missing_audit_source`
- `healthy_window`

## Stair Coefficient

`AGGREGATION_STAIR_COEFFICIENT` is used in the aggregation layer to convert sustained pressure into stepped severity.

Example:

- if usage just crosses the threshold, severity stays low
- if usage keeps increasing by each stair multiplier, severity rises from low to medium, high, and critical

This is meant to make the event layer more explainable than a single fixed threshold.

## Current Limitations

- GPU and token analysis are snapshot-based unless you add a collector
- audit-log analysis depends on PostgreSQL availability
- case-based historical insight and LLM explanation are not implemented yet
- RRD historical feature extraction is not yet imported into this MVP
