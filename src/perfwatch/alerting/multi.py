from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from perfwatch.storage.models import AlertEvent


@dataclass
class MultiAlerter:
    alerters: Sequence[object]

    def send(self, alert: AlertEvent) -> None:
        for a in self.alerters:
            a.send(alert)
