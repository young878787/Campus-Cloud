# PVE Placement Advisor Implementation Status

## Current Scope

This service has been repurposed from log analytics into a PVE placement advisor.

Current implemented scope:

- standalone FastAPI service `ai-pve-placement-advisor`
- direct Proxmox node and guest reads
- env snapshot fallback for node data
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

## Implemented Planner Logic

- [x] CPU safe headroom calculation
- [x] memory safe headroom calculation
- [x] disk safe headroom calculation
- [x] automatic balanced placement
- [x] partial-fit detection
- [x] placement-blocked detection

## Preserved Basic Node Log

- [x] node status overview
- [x] node CPU / memory / disk visibility
- [x] placement recommendation view
- [x] source health display

## Remaining Gaps

- [ ] pull request / backend approval flow integration
- [ ] directly reading the exact backend request record as placement input
- [ ] historical placement comparison for similar past requests
- [ ] node-level storage pool awareness
- [ ] VM template / LXC template specific constraints
- [ ] automatic provisioning after recommendation approval
- [ ] richer tests around placement scoring

## Next Suggested Work

1. Connect placement input directly to the backend VM/LXC request form model.
2. Add storage-pool and template constraints so recommendations better match real provisioning rules.
3. Record each placement recommendation to compare future similar requests.
4. Add automated tests for full fit, partial fit, and no-capacity cases.
