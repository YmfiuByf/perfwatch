from __future__ import annotations

from typing import Any, Protocol


class Alerter(Protocol):
    """Alert sender interface.

    Any alerter should implement a single send() method.
    """

    def send(self, alert: Any) -> None:
        ...
