from __future__ import annotations

import time
from dataclasses import dataclass

from perfwatch.storage.models import AlertEvent
from perfwatch.storage.sqlite import SQLiteStore


def _now_unix() -> int:
    return int(time.time())


def build_dedup_key(alert: AlertEvent, mode: str = "key_severity_title") -> str:
    # key_only: probe only (最粗粒度)
    if mode == "key_only":
        return f"{alert.probe}"

    # 默认：probe + severity + title（更精细，不同告警类型不互相压制）
    return f"{alert.probe}|{alert.severity}|{alert.title}"


@dataclass
class AlertGate:
    store: SQLiteStore
    cooldown_sec: int
    dedup_mode: str = "key_severity_title"

    def allow(self, alert: AlertEvent) -> bool:
        if self.cooldown_sec <= 0:
            return True

        key = build_dedup_key(alert, self.dedup_mode)
        last = self.store.get_last_sent_ts(key)
        now = _now_unix()

        if last is None or (now - last) >= self.cooldown_sec:
            self.store.upsert_last_sent_ts(key, now)
            return True

        return False
