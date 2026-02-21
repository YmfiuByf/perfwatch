from __future__ import annotations

import sys
import threading
from pathlib import Path

from perfwatch.config import load_config
from perfwatch.utils.logging import setup_logging, get_logger
from perfwatch.storage.sqlite import SQLiteStore
from perfwatch.collector.demo import PingCollector, HttpCollector
from perfwatch.pipeline.normalize import normalize_metric
from perfwatch.scheduler.job import IntervalScheduler
from perfwatch.web.api import start_web_server

from perfwatch.rules.loader import RulesManager

from perfwatch.alerting.dedup import AlertGate
from perfwatch.alerting.console import ConsoleAlerter
from perfwatch.alerting.multi import MultiAlerter
from perfwatch.alerting.webhook import WebhookAlerter

from perfwatch.ai.deepseek import DeepSeekAnalyzer, DeepSeekConfig


log = get_logger(__name__)


def _build_demo_pipeline(
    cfg,
    store: SQLiteStore,
    analyzer: DeepSeekAnalyzer,
    gate: AlertGate,
):
    collectors = [
        PingCollector(host=cfg.ping_host, timeout_sec=cfg.ping_timeout_sec),
        HttpCollector(url=cfg.http_url, timeout_sec=cfg.http_timeout_sec),
    ]

    rules_mgr = RulesManager.from_config(cfg)

    alerters = [ConsoleAlerter()]
    if cfg.webhook_enabled and cfg.webhook_url:
        alerters.append(
            WebhookAlerter(
                url=cfg.webhook_url,
                timeout_sec=cfg.webhook_timeout_sec,
                min_severity=cfg.webhook_min_severity,
                auth_header=cfg.webhook_auth_header,
                token=cfg.webhook_token,
                token_prefix=cfg.webhook_token_prefix,
            )

        )
    alerter = MultiAlerter(alerters)

    def run_once() -> None:
        # Hot reload rules if rules.yaml changed
        rules_mgr.refresh_if_needed()

        for c in collectors:
            m = c.collect()
            nm = normalize_metric(m)

            # 1) store metric (always)
            store.insert_metric(nm)

            # 2) evaluate rules
            recent = store.fetch_recent_latency(nm.probe, limit=200)
            for r in rules_mgr.rules:
                alert = r.evaluate(nm, recent=recent)
                if alert is None:
                    continue

                # 3) gate first (dedup/cooldown) to avoid spamming + avoid wasting AI calls
                if not gate.allow(alert):
                    continue

                # 4) AI analysis
                try:
                    ai_text = analyzer.analyze(
                        alert=alert,
                        metric=nm,
                        recent=recent,
                    )
                except Exception as e:
                    ai_text = f"AI analyze error: {e}"

                if ai_text:
                    # Append AI text into message so that DB + Web UI can show it easily.
                    msg = (alert.message or "").rstrip()
                    msg = f"{msg}\n\n---\nAI分析（DeepSeek）:\n{ai_text}".strip()
                    alert = alert.__class__(
                        ts_unix=alert.ts_unix,
                        probe=alert.probe,
                        severity=alert.severity,
                        title=alert.title,
                        message=msg,
                    )

                # 5) store + send (only for allowed alerts)
                store.insert_alert(alert)
                alerter.send(alert)

    return run_once


def main(argv: list[str] | None = None) -> int:
    setup_logging()
    cfg = load_config()
    log.info("PerfWatch starting...")

    # Ensure data dir exists if DB_PATH uses it
    db_path = Path(cfg.db_path)
    if db_path.parent:
        db_path.parent.mkdir(parents=True, exist_ok=True)

    store = SQLiteStore(cfg.db_path)
    store.init_schema()

    gate = AlertGate(
        store=store,
        cooldown_sec=cfg.alert_cooldown_sec,
        dedup_mode=cfg.alert_dedup_mode,
    )

    analyzer = DeepSeekAnalyzer(
        DeepSeekConfig(
            enabled=cfg.ai_enabled and bool(cfg.deepseek_api_key),
            api_key=cfg.deepseek_api_key,
            base_url=cfg.deepseek_base_url,
            model=cfg.deepseek_model,
            timeout_sec=cfg.ai_timeout_sec,
            max_tokens=cfg.ai_max_tokens,
            cooldown_sec=cfg.ai_cooldown_sec,
            on_severity=set(
                s.strip() for s in cfg.ai_on_severity.split(",") if s.strip()
            ),
        )
    )

    job = _build_demo_pipeline(cfg, store, analyzer, gate)

    # Optional web server
    if cfg.web_enabled:
        t = threading.Thread(
            target=start_web_server,
            args=(cfg, store),
            daemon=True,
            name="perfwatch-web",
        )
        t.start()
        log.info("Web API enabled on http://%s:%d", cfg.web_host, cfg.web_port)

    sched = IntervalScheduler(interval_sec=cfg.interval_sec, job=job)

    try:
        sched.run_forever()
    except KeyboardInterrupt:
        log.info("Received Ctrl+C. Shutting down...")
        return 0
    except Exception:
        log.exception("Fatal error")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
