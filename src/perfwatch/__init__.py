"""PerfWatch package.

A minimal end-to-end "performance watcher + alerting" project:
- Collect metrics (demo collectors: ping/http)
- Normalize metrics for consistent storage/rules
- Store to SQLite for history and inspection
- Evaluate alert rules
- Emit alerts to console (extensible to Slack/Email/Webhook)
- Optionally expose a built-in Web API to inspect latest metrics/alerts
"""

__all__ = ["main"]