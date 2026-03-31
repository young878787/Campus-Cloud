# PVE Resource Simulator

Standalone FastAPI prototype for testing PVE-style resource scheduling.

## Features

- Define any number of servers with CPU, RAM, Disk, and GPU capacity.
- Seed each server with existing used resources.
- Add multiple VM templates with no fixed placement limit.
- Auto-place workloads until no enabled VM template fits anywhere.
- Pick the destination server using weighted dominant share plus contention penalties.
- Allow CPU overcommit while keeping a RAM safety buffer.
- Use historical same-type hourly weighted mean baselines and P95 peaks when analytics exist.
- Export historical `average`, `trend`, and `peak` signals from monthly analytics.
- Try a small local rebalance before declaring `no_fit`.
- Visualize every placement step through a static UI.

## Current Placement Model

The simulator currently separates three layers:

- `average_*`: weighted mean utilization from monthly analytics.
- `trend_*`: EWMA trend derived from time-ordered weighted samples.
- `peak_*`: weighted P95 utilization.

For live placement, the simulator currently uses:

- The highest of hour-specific `hourly[*]`, profile `trend_*`, and profile `average_*` for CPU and RAM baseline sizing.
- Peak guard from hour-specific `peak_*`, then profile `peak_*`.

Effective requested resources are calculated conservatively:

- CPU: historical ratio with margin `1.4`, floored at `35%` of requested, capped by requested.
- RAM: historical ratio with margin `1.15`, floored at `50%` of requested, capped by requested.
- Disk and GPU: currently use requested values directly.

Server choice is based on the lowest projected score after placement:

- weighted dominant share across CPU, RAM, Disk, and optional GPU
- contention penalty for CPU and Disk
- hard overflow penalty for RAM
- soft penalty for elevated host `loadavg`
- tie-breakers: average weighted share, physical CPU share, placement count, server name

If no node fits directly and `allow_rebalance=true`, the simulator searches a local rebalance of up to 2 moves and applies a migration cost when scoring move targets.

## Parameter Tuning Notes

Not every constant here should be treated as a machine-learned hyperparameter.

As a practical rule:

- Keep structural constants stable first: `EPSILON`, margins, floors, peak margins, rebalance move limit, migration cost.
- Only calibrate policy constants later: CPU overcommit, RAM usable ratio, safe/max share thresholds, loadavg thresholds, and share weights.

Plain-language version:

- Some numbers define the shape of the simulator itself, so changing them too early just makes behavior harder to reason about.
- The numbers most worth tuning are the ones that reflect campus operating policy, such as how aggressive CPU overcommit should be or how much host loadavg should lower placement priority.
- If you want to optimize them in the future, replay historical data first and use offline evaluation or search-based tuning before considering AI-driven optimization.

## Run

```bash
cd "pve_ resource_simulator"
pip install -r requirements.txt
python main.py
```

Open `http://127.0.0.1:8012`.

Allocation logic notes:

```bash
pve_ resource_simulator/docs/allocation-logic.md
```

Monthly analytics page:

```bash
http://127.0.0.1:8012/monthly-analytics
```

This project also includes `pve_ resource_simulator/.env.example`, and the local
`pve_ resource_simulator/.env` can use the same `PROXMOX_*` naming as the backend.

Optional Proxmox settings for the analytics page:

```bash
PROXMOX_HOST=192.168.100.2
PROXMOX_USER=ccapiuser@pve
PROXMOX_PASSWORD=your-password
PROXMOX_VERIFY_SSL=false
PROXMOX_API_TIMEOUT=20
PROXMOX_ISO_STORAGE=ISO
PROXMOX_DATA_STORAGE=data-ssd-2
PVE_ANALYTICS_TIMEZONE=Asia/Taipei
```

The analytics page reads these values from process env, the repo root `.env`, or
`pve_ resource_simulator/.env`.

## Test

```bash
cd "pve_ resource_simulator"
pytest
```
