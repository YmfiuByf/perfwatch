from __future__ import annotations

from perfwatch.storage.models import Metric


def normalize_metric(m: Metric) -> Metric:
    """Normalizes a Metric for consistent storage and rule evaluation.

    - Normalizes probe prefix to "ping:" / "http:"
    - Converts invalid latency (e.g., negative) to None
    - Trims detail to a bounded size
    """
    probe = m.probe.strip()

    if probe.lower().startswith("ping:"):
        probe = "ping:" + probe.split(":", 1)[1]
    elif probe.lower().startswith("http:"):
        probe = "http:" + probe.split(":", 1)[1]

    latency_ms = m.latency_ms
    if latency_ms is not None and latency_ms < 0:
        latency_ms = None

    detail = m.detail
    if detail is not None:
        detail = detail.strip()
        if len(detail) > 800:
            detail = detail[:800]

    return Metric(
        ts_unix=m.ts_unix,
        probe=probe,
        ok=bool(m.ok),
        latency_ms=latency_ms,
        detail=detail,
    )