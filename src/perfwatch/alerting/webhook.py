from __future__ import annotations

import json
from typing import Any, Dict, Optional

import urllib.request
import urllib.error

from perfwatch.utils.logging import get_logger

log = get_logger(__name__)


def _sev_rank(sev: str) -> int:
    s = (sev or "").lower()
    if s in ("critical", "crit", "fatal"):
        return 3
    if s in ("warn", "warning"):
        return 2
    if s in ("info",):
        return 1
    return 0


class WebhookAlerter:
    """Send alerts to a HTTP webhook endpoint.

    This alerter only depends on alert having these attributes:
    - ts_unix, probe, severity, title, message
    """

    def __init__(
        self,
        url: str,
        timeout_sec: float = 5.0,
        min_severity: str = "warn",
        auth_header: Optional[str] = None,
        token: Optional[str] = None,
        token_prefix: Optional[str] = None,
    ) -> None:
        self._url = url
        self._timeout_sec = float(timeout_sec)
        self._min_rank = _sev_rank(min_severity)

        # If auth_header is provided, it is used as the header key.
        # Otherwise, default to "Authorization" when token is provided.
        self._auth_header = auth_header
        self._token = token

        # If token_prefix is provided, it will be prepended like "Bearer <token>".
        # Common choices: "Bearer", "Token". If None/empty, raw token is used.
        self._token_prefix = token_prefix

    def _build_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "perfwatch/1.0",
        }

        # ---- Minimal enhancement starts here ----
        # Support:
        # 1) auth_header + token  -> {auth_header: token}
        # 2) token only          -> {"Authorization": token}
        # 3) optional prefix     -> {"Authorization": "Bearer <token>"} etc.
        if self._token:
            header_name = self._auth_header or "Authorization"
            token_value = self._token

            if self._token_prefix:
                p = self._token_prefix.strip()
                if p:
                    token_value = f"{p} {token_value}"

            headers[header_name] = token_value
        # ---- Minimal enhancement ends here ----

        return headers

    def send(self, alert: Any) -> None:
        sev = getattr(alert, "severity", "") or ""
        if _sev_rank(sev) < self._min_rank:
            return

        payload = {
            "ts_unix": getattr(alert, "ts_unix", None),
            "probe": getattr(alert, "probe", None),
            "severity": sev,
            "title": getattr(alert, "title", None),
            "message": getattr(alert, "message", None),
        }

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self._url,
            data=data,
            headers=self._build_headers(),
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self._timeout_sec) as resp:
                resp.read()
        except urllib.error.HTTPError as e:
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                body = ""
            log.error("Webhook failed: HTTP %s body=%s", e.code, body)
        except Exception as e:
            log.error("Webhook failed: %s", e)
