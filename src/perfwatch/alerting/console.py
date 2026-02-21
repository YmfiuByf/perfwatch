from __future__ import annotations

from perfwatch.storage.models import AlertEvent
from perfwatch.utils.logging import get_logger

log = get_logger(__name__)


class ConsoleAlerter:
    def send(self, alert: AlertEvent) -> None:
        # Minimal alert sink for development and local testing.
        if alert.severity == "critical":
            log.error("[ALERT][%s] %s - %s", alert.probe, alert.title, alert.message)
        else:
            log.warning("[ALERT][%s] %s - %s", alert.probe, alert.title, alert.message)