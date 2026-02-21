from __future__ import annotations

from abc import ABC, abstractmethod
from perfwatch.storage.models import Metric, AlertEvent


class Rule(ABC):
    @abstractmethod
    def evaluate(self, metric: Metric, recent: list[float]) -> AlertEvent | None:
        """Returns AlertEvent when triggered; otherwise returns None."""
        raise NotImplementedError