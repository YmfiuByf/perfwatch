from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import requests

from perfwatch.storage.models import Metric, AlertEvent


@dataclass
class DeepSeekConfig:
    enabled: bool
    api_key: str
    base_url: str
    model: str
    timeout_sec: int
    max_tokens: int
    cooldown_sec: int
    on_severity: set[str]  # {"critical","warn"}


class DeepSeekAnalyzer:
    """Call DeepSeek Chat Completions to generate alert triage hints.

    Design choices:
    - Keep DB schema unchanged: analysis text is appended into alert.message.
    - Add simple per-probe cooldown to avoid spamming/cost.
    """

    def __init__(self, cfg: DeepSeekConfig):
        self.cfg = cfg
        self._last_call_by_probe: dict[str, int] = {}

    def should_analyze(self, alert: AlertEvent) -> bool:
        if not self.cfg.enabled:
            return False
        if alert.severity not in self.cfg.on_severity:
            return False

        now = int(time.time())
        last = self._last_call_by_probe.get(alert.probe, 0)
        if now - last < self.cfg.cooldown_sec:
            return False
        return True

    def analyze(self, metric: Metric, recent: list[float], alert: AlertEvent) -> Optional[str]:
        """Return analysis text, or None if skipped/failed."""
        if not self.should_analyze(alert):
            return None

        now = int(time.time())
        self._last_call_by_probe[alert.probe] = now

        url = self.cfg.base_url.rstrip("/") + "/chat/completions"

        # Keep prompt short & practical (SRE-style triage).
        # Output Chinese, but with simple wording for readability.
        system_msg = (
            "你是资深SRE/后端性能工程师。"
            "给出简短、可执行的排查建议，避免空话。"
            "回答用中文，条目化。"
        )

        # Recent history summary (avoid huge payload)
        if recent:
            recent_tail = recent[-20:]
            recent_str = ", ".join(f"{x:.1f}" for x in recent_tail)
        else:
            recent_str = "(no history)"

        user_msg = f"""这是一次性能监控告警，请你做快速初步分析（不是最终结论）：

[Probe] {metric.probe}
[Timestamp] {metric.ts_unix}
[OK] {metric.ok}
[Latency_ms] {metric.latency_ms}
[Detail] {metric.detail}

[Alert]
- severity: {alert.severity}
- title: {alert.title}
- message: {alert.message}

[Recent latency history (oldest->newest, last 20)]
{recent_str}

请输出：
1) 最可能的原因（给出 2-3 个候选，按可能性排序）
2) 接下来最值得做的 3 个排查动作（要具体）
3) 如果是 TLS/证书、DNS、网络、目标站点限制等常见原因，请明确指出“如何验证”
"""

        payload = {
            "model": self.cfg.model,
            "messages": [
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            "stream": False,
            "max_tokens": self.cfg.max_tokens,
            "temperature": 0.2,
        }

        headers = {
            "Content-Type": "application/json",
            # DeepSeek uses OpenAI-compatible auth header:
            # Authorization: Bearer ${DEEPSEEK_API_KEY}
            "Authorization": f"Bearer {self.cfg.api_key}",
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=self.cfg.timeout_sec)
            resp.raise_for_status()
            data = resp.json()
            text = data["choices"][0]["message"]["content"]
            return text.strip()
        except Exception as e:
            # Do not crash the whole pipeline if AI fails.
            return f"(AI analysis failed: {e})"
