# PVE Placement Advisor Implementation Status

## Current Scope

This service has been repurposed from log analytics into a PVE placement advisor.

Current implemented scope:

- standalone FastAPI service `ai-pve-placement-advisor`
- direct Proxmox node and guest reads
- env snapshot fallback for node data
- optional backend VM request traffic ingestion
- cluster summary focused on CPU, memory, disk, guest density, and user pressure
- safe-headroom node capacity calculation
- identical workload placement recommendation
- built-in web UI with placement form, node capacity view, and recommendations

## Implemented API

- [x] `GET /api/v1/analyze`
- [x] `POST /api/v1/placement/recommend`
- [x] `POST /api/v1/explain`
- [x] `POST /api/v1/chat`
- [x] `GET /api/v1/sources/preview`
- [x] `GET /api/v1/metrics`

## Implemented Planner Logic

- [x] CPU safe headroom calculation
- [x] memory safe headroom calculation
- [x] disk safe headroom calculation
- [x] running-only guest density counting
- [x] automatic balanced placement
- [x] weighted headroom scoring
- [x] GPU requirement constraint (`gpu_required`)
- [x] partial-fit detection
- [x] placement-blocked detection
- [x] source retry/backoff
- [x] source TTL cache

## Preserved Basic Node Log

- [x] node status overview
- [x] node CPU / memory / disk visibility
- [x] placement recommendation view
- [x] source health display

## Test Coverage

- [x] full-fit placement case
- [x] partial-fit placement case
- [x] running-only guest counting case
- [x] GPU-constrained placement case

## Remaining Gaps

- [ ] pull request / backend approval flow integration
- [ ] directly reading single request record by id as placement input
- [ ] historical placement comparison for similar past requests
- [ ] node-level storage pool awareness
- [ ] VM template / LXC template specific constraints
- [ ] automatic provisioning after recommendation approval
- [ ] end-to-end tests across API routes and source fallback chains

## Next Suggested Work

1. Add a direct endpoint mode that consumes backend request id and converts it to placement input.
2. Add storage-pool and template constraints so recommendations better match real provisioning rules.
3. Record each placement recommendation to compare future similar requests.
4. Add API-level integration tests for retry/cache/source-fallback behavior.
