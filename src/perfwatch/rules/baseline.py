from __future__ import annotations

import time
from dataclasses import dataclass

from perfwatch.rules.base import Rule
from perfwatch.storage.models import Metric, AlertEvent


def _now_unix() -> int:
    return int(time.time())


def _percentile(values: list[float], p: float) -> float:
    # p in [0, 1]
    if not values:
        raise ValueError("empty values")
    vs = sorted(values)
    if len(vs) == 1:
        return vs[0]
    idx = int(round(p * (len(vs) - 1)))
    idx = max(0, min(idx, len(vs) - 1))
    return vs[idx]


@dataclass
class BaselineRule(Rule):
    probe_prefix: str
    window_size: int
    method: str               # "mean" | "p90" | "p95"
    factor_warn: float
    factor_crit: float
    min_baseline_ms: float = 0.0

    def evaluate(self, metric: Metric, recent: list[float]) -> AlertEvent | None:
        # Only handle matching probes
        if not metric.probe.startswith(self.probe_prefix):
            return None

        # If probe failed, treat as critical signal
        if not metric.ok:
            return AlertEvent(
                ts_unix=_now_unix(),
                probe=metric.probe,
                severity="critical",
                title="Probe failed",
                message=f"{metric.probe} failed. detail={metric.detail or ''}",
            )

        if metric.latency_ms is None:
            return None

        # Need enough history to form a baseline
        if self.window_size <= 0:
            return None

        hist = recent[-self.window_size :] if len(recent) >= 1 else []
        if len(hist) < max(5, min(self.window_size, 10)):
            # Too few points => skip to avoid noisy alerts
            return None

        if self.method == "mean":
            baseline = sum(hist) / len(hist)
        elif self.method == "p90":
            baseline = _percentile(hist, 0.90)
        elif self.method == "p95":
            baseline = _percentile(hist, 0.95)
        else:
            return None

        baseline = max(baseline, float(self.min_baseline_ms))
        lat = float(metric.latency_ms)

        crit_th = baseline * float(self.factor_crit)
        warn_th = baseline * float(self.factor_warn)

        if lat >= crit_th:
            return AlertEvent(
                ts_unix=_now_unix(),
                probe=metric.probe,
                severity="critical",
                title="Latency anomalous (baseline)",
                message=(
                    f"{metric.probe} latency {lat:.1f} ms >= baseline {baseline:.1f} ms * "
                    f"{self.factor_crit:.2f} ({crit_th:.1f} ms)"
                ),
            )

        if lat >= warn_th:
            return AlertEvent(
                ts_unix=_now_unix(),
                probe=metric.probe,
                severity="warn",
                title="Latency elevated (baseline)",
                message=(
                    f"{metric.probe} latency {lat:.1f} ms >= baseline {baseline:.1f} ms * "
                    f"{self.factor_warn:.2f} ({warn_th:.1f} ms)"
                ),
            )

        return None
