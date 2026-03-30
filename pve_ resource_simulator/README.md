# PVE Resource Simulator

Standalone FastAPI prototype for testing PVE-style resource scheduling.

## Features

- Define any number of servers with CPU, RAM, Disk, and GPU capacity.
- Seed each server with existing used resources.
- Add multiple VM templates with no fixed placement limit.
- Auto-place workloads until no enabled VM template fits anywhere.
- Pick the destination server using the minimum dominant-share rule.
- Visualize every placement step through a static UI.

## Run

```bash
cd "pve_ resource_simulator"
pip install -r requirements.txt
python main.py
```

Open `http://127.0.0.1:8012`.

## Test

```bash
cd "pve_ resource_simulator"
pytest
```
