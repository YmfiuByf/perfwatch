from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Metric:
    ts_unix: int
    probe: str                 # e.g. "ping:8.8.8.8" or "http:https://example.com"
    ok: bool
    latency_ms: Optional[float]
    detail: Optional[str]


@dataclass(frozen=True)
class AlertEvent:
    ts_unix: int
    probe: str
    severity: str              # "warn" | "critical"
    title: str
    message: str