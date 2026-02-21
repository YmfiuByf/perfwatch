from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    # core
    db_path: str
    interval_sec: int

    # web
    web_enabled: bool
    web_host: str
    web_port: int

    # rules
    rules_path: str
    rules_reload_sec: int

    # collectors
    ping_host: str
    ping_timeout_sec: int

    http_url: str
    http_timeout_sec: int

    # thresholds (ms) - kept for backward compatibility / fallback
    ping_latency_warn_ms: float
    ping_latency_crit_ms: float
    http_latency_warn_ms: float
    http_latency_crit_ms: float

    # alerting
    alert_cooldown_sec: int
    alert_dedup_mode: str

    # webhook
    webhook_enabled: bool
    webhook_url: str
    webhook_timeout_sec: int
    webhook_min_severity: str

    webhook_auth_header: str        
    webhook_token: str              
    webhook_token_prefix: str       


    # AI (DeepSeek)
    ai_enabled: bool
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str
    ai_timeout_sec: int
    ai_max_tokens: int
    ai_cooldown_sec: int
    ai_on_severity: str





def _get_bool(name: str, default: str = "0") -> bool:
    v = os.getenv(name, default).strip().lower()
    return v in ("1", "true", "yes", "y", "on")


def load_config() -> Config:
    # Load .env from current working directory (project root)
    load_dotenv(override=False)

    return Config(
        db_path=os.getenv("DB_PATH", "./data/perfwatch.db"),
        interval_sec=int(os.getenv("INTERVAL_SEC", "30")),

        web_enabled=_get_bool("WEB_ENABLED", "0"),
        web_host=os.getenv("WEB_HOST", "127.0.0.1"),
        web_port=int(os.getenv("WEB_PORT", "8080")),

        rules_path=os.getenv("RULES_PATH", "./rules.yaml"),
        rules_reload_sec=int(os.getenv("RULES_RELOAD_SEC", "5")),

        ping_host=os.getenv("PING_HOST", "8.8.8.8"),
        ping_timeout_sec=int(os.getenv("PING_TIMEOUT_SEC", "2")),

        http_url=os.getenv("HTTP_URL", "https://example.com"),
        http_timeout_sec=int(os.getenv("HTTP_TIMEOUT_SEC", "5")),

        ping_latency_warn_ms=float(os.getenv("PING_LATENCY_WARN_MS", "250")),
        ping_latency_crit_ms=float(os.getenv("PING_LATENCY_CRIT_MS", "600")),
        http_latency_warn_ms=float(os.getenv("HTTP_LATENCY_WARN_MS", "800")),
        http_latency_crit_ms=float(os.getenv("HTTP_LATENCY_CRIT_MS", "1500")),

        alert_cooldown_sec=int(os.getenv("ALERT_COOLDOWN_SEC", "300")),
        alert_dedup_mode=os.getenv("ALERT_DEDUP_MODE", "key_severity_title"),

        webhook_enabled=_get_bool("WEBHOOK_ENABLED", "0"),
        webhook_url=os.getenv("WEBHOOK_URL", ""),
        webhook_timeout_sec=int(os.getenv("WEBHOOK_TIMEOUT_SEC", "5")),
        webhook_min_severity=os.getenv("WEBHOOK_MIN_SEVERITY", "warn"),

        webhook_auth_header=os.getenv("WEBHOOK_AUTH_HEADER", "").strip(),
        webhook_token=os.getenv("WEBHOOK_TOKEN", "").strip(),
        webhook_token_prefix=os.getenv("WEBHOOK_TOKEN_PREFIX", "").strip(),




        ai_enabled=_get_bool("AI_ENABLED", "0"),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", "").strip(),
        deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip(),
        deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat").strip(),
        ai_timeout_sec=int(os.getenv("AI_TIMEOUT_SEC", "20")),
        ai_max_tokens=int(os.getenv("AI_MAX_TOKENS", "300")),
        ai_cooldown_sec=int(os.getenv("AI_COOLDOWN_SEC", "120")),
        ai_on_severity=os.getenv("AI_ON_SEVERITY", "critical").strip(),


    )
