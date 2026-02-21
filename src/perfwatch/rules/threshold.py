from __future__ import annotations

import time
from dataclasses import dataclass

from perfwatch.config import Config
from perfwatch.rules.base import Rule
from perfwatch.storage.models import Metric, AlertEvent


def _now_unix() -> int:
    return int(time.time())


@dataclass
class ThresholdRule(Rule):
    """
    Backward-compatible threshold rule driven by env Config.
    It decides thresholds by probe type ("ping:" / "http:").
    """
    ping_warn_ms: float
    ping_crit_ms: float
    http_warn_ms: float
    http_crit_ms: float

    @staticmethod
    def from_config(cfg: Config) -> "ThresholdRule":
        return ThresholdRule(
            ping_warn_ms=cfg.ping_latency_warn_ms,
            ping_crit_ms=cfg.ping_latency_crit_ms,
            http_warn_ms=cfg.http_latency_warn_ms,
            http_crit_ms=cfg.http_latency_crit_ms,
        )

    def evaluate(self, metric: Metric, recent: list[float]) -> AlertEvent | None:
        # Always alert if probe failed.
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

        if metric.probe.startswith("ping:"):
            warn, crit = self.ping_warn_ms, self.ping_crit_ms
        elif metric.probe.startswith("http:"):
            warn, crit = self.http_warn_ms, self.http_crit_ms
        else:
            return None

        lat = float(metric.latency_ms)
        if lat >= float(crit):
            return AlertEvent(
                ts_unix=_now_unix(),
                probe=metric.probe,
                severity="critical",
                title="Latency critical",
                message=f"{metric.probe} latency {lat:.1f} ms >= {float(crit):.1f} ms",
            )
        if lat >= float(warn):
            return AlertEvent(
                ts_unix=_now_unix(),
                probe=metric.probe,
                severity="warn",
                title="Latency high",
                message=f"{metric.probe} latency {lat:.1f} ms >= {float(warn):.1f} ms",
            )
        return None


@dataclass
class PrefixThresholdRule(Rule):
    """
    YAML-driven threshold rule.
    Applies to probes whose name starts with probe_prefix.
    """
    probe_prefix: str
    warn_ms: float
    crit_ms: float

    def evaluate(self, metric: Metric, recent: list[float]) -> AlertEvent | None:
        if not metric.probe.startswith(self.probe_prefix):
            return None

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

        lat = float(metric.latency_ms)
        if lat >= float(self.crit_ms):
            return AlertEvent(
                ts_unix=_now_unix(),
                probe=metric.probe,
                severity="critical",
                title="Latency critical",
                message=f"{metric.probe} latency {lat:.1f} ms >= {float(self.crit_ms):.1f} ms",
            )

        if lat >= float(self.warn_ms):
            return AlertEvent(
                ts_unix=_now_unix(),
                probe=metric.probe,
                severity="warn",
                title="Latency high",
                message=f"{metric.probe} latency {lat:.1f} ms >= {float(self.warn_ms):.1f} ms",
            )

        return None
