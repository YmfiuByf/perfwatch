from __future__ import annotations

import platform
import subprocess
import time
from dataclasses import dataclass

import requests

from perfwatch.collector.base import Collector
from perfwatch.storage.models import Metric


def _now_unix() -> int:
    return int(time.time())


@dataclass
class PingCollector(Collector):
    host: str
    timeout_sec: int = 2

    def collect(self) -> Metric:
        start = time.perf_counter()
        system = platform.system().lower()

        if system == "windows":
            # Windows ping: -n count, -w timeout(ms)
            cmd = ["ping", "-n", "1", "-w", str(self.timeout_sec * 1000), self.host]
        else:
            # Unix ping: -c count, -W timeout(sec)
            cmd = ["ping", "-c", "1", "-W", str(self.timeout_sec), self.host]

        try:
            p = subprocess.run(cmd, capture_output=True, text=True)
            end = time.perf_counter()
            ok = (p.returncode == 0)
            latency_ms = (end - start) * 1000.0
            detail = (p.stdout or p.stderr).strip()[:800]
            return Metric(
                ts_unix=_now_unix(),
                probe=f"ping:{self.host}",
                ok=ok,
                latency_ms=latency_ms,
                detail=detail,
            )
        except Exception as e:
            end = time.perf_counter()
            return Metric(
                ts_unix=_now_unix(),
                probe=f"ping:{self.host}",
                ok=False,
                latency_ms=(end - start) * 1000.0,
                detail=f"ping exception: {e}",
            )


@dataclass
class HttpCollector(Collector):
    url: str
    timeout_sec: int = 5

    def collect(self) -> Metric:
        start = time.perf_counter()
        try:
            r = requests.get(self.url, timeout=self.timeout_sec)
            end = time.perf_counter()
            ok = (200 <= r.status_code < 400)
            latency_ms = (end - start) * 1000.0
            detail = f"status={r.status_code} bytes={len(r.content)}"
            return Metric(
                ts_unix=_now_unix(),
                probe=f"http:{self.url}",
                ok=ok,
                latency_ms=latency_ms,
                detail=detail,
            )
        except Exception as e:
            end = time.perf_counter()
            return Metric(
                ts_unix=_now_unix(),
                probe=f"http:{self.url}",
                ok=False,
                latency_ms=(end - start) * 1000.0,
                detail=f"http exception: {e}",
            )