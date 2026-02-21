# PerfWatch (Docker)

PerfWatch is a lightweight monitoring + alerting tool packaged for easy startup with Docker. It collects simple probe metrics, stores them in SQLite, evaluates threshold rules, and exposes a small web dashboard/API. Optional features include alert deduplication/cooldown, webhook delivery (with optional auth header/token), and AI-assisted analysis (DeepSeek) appended to alert records.

## Features
- Metric collection (demo probes: ping / HTTP)
- Normalize + store metrics/alerts in SQLite
- Threshold rules (optional hot reload via `rules.yaml`)
- Alert deduplication + cooldown to reduce noise
- Console alerts + optional webhook notification
- Web dashboard + JSON APIs (`/`, `/health`, `/metrics`, `/alerts`, `/rules`)
- Optional AI analysis (DeepSeek) attached to alert messages

## Prerequisites
- Docker Desktop (Windows/macOS) or Docker Engine (Linux)

## Quick Start (Docker)
From the project root:

```bash
docker build -t perfwatch:dev .
docker run --rm -p 8080:8080 --env-file .env perfwatch:dev
```

![Result](results/preview.png)
