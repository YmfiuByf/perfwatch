from __future__ import annotations

from abc import ABC, abstractmethod
from perfwatch.storage.models import Metric


class Collector(ABC):
    @abstractmethod
    def collect(self) -> Metric:
        """Collects a single Metric sample."""
        raise NotImplementedError