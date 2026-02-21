from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from perfwatch.utils.logging import get_logger

log = get_logger(__name__)


@dataclass
class IntervalScheduler:
    interval_sec: int
    job: Callable[[], None]

    def run_forever(self) -> None:
        if self.interval_sec <= 0:
            raise ValueError("interval_sec must be > 0")

        log.info("Scheduler started. interval=%ds", self.interval_sec)

        while True:
            t0 = time.perf_counter()
            try:
                self.job()
            except Exception:
                # Failures are logged; the next tick will retry.
                log.exception("Job failed (will retry next tick)")

            elapsed = time.perf_counter() - t0
            sleep_sec = max(0.0, self.interval_sec - elapsed)
            time.sleep(sleep_sec)