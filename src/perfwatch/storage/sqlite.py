from __future__ import annotations

import os
import sqlite3
from typing import Any

from perfwatch.storage.models import Metric, AlertEvent


class SQLiteStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_parent_dir()

    def _ensure_parent_dir(self) -> None:
        # Creates the parent directory if missing.
        parent = os.path.dirname(self.db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        # Uses short-lived connections; enables WAL for better concurrency.
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def init_schema(self) -> None:
        # Ensures required tables and indexes exist.
        with self._connect() as conn:
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts_unix INTEGER NOT NULL,
                    probe TEXT NOT NULL,
                    ok INTEGER NOT NULL,
                    latency_ms REAL,
                    detail TEXT
                );
                '''
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_metrics_probe_ts ON metrics (probe, ts_unix);"
            )

            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ts_unix INTEGER NOT NULL,
                    probe TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL
                );
                '''
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_alerts_probe_ts ON alerts (probe, ts_unix);"
            )
            
            conn.execute(
                '''
                CREATE TABLE IF NOT EXISTS alert_state (
                    dedup_key TEXT PRIMARY KEY,
                    last_sent_ts INTEGER NOT NULL
                );
                '''
            )

            conn.commit()

    def insert_metric(self, m: Metric) -> None:
        with self._connect() as conn:
            conn.execute(
                '''
                INSERT INTO metrics (ts_unix, probe, ok, latency_ms, detail)
                VALUES (?, ?, ?, ?, ?);
                ''',
                (m.ts_unix, m.probe, 1 if m.ok else 0, m.latency_ms, m.detail),
            )
            conn.commit()

    def insert_alert(self, a: AlertEvent) -> None:
        with self._connect() as conn:
            conn.execute(
                '''
                INSERT INTO alerts (ts_unix, probe, severity, title, message)
                VALUES (?, ?, ?, ?, ?);
                ''',
                (a.ts_unix, a.probe, a.severity, a.title, a.message),
            )
            conn.commit()

    def fetch_recent_latency(self, probe: str, limit: int = 50) -> list[float]:
        # Returns values ordered from oldest -> newest.
        with self._connect() as conn:
            cur = conn.execute(
                '''
                SELECT latency_ms
                FROM metrics
                WHERE probe = ? AND ok = 1 AND latency_ms IS NOT NULL
                ORDER BY ts_unix DESC
                LIMIT ?;
                ''',
                (probe, limit),
            )
            vals = [r[0] for r in cur.fetchall() if r[0] is not None]
            return list(reversed(vals))  # oldest->newest

    def fetch_latest_metrics(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            cur = conn.execute(
                '''
                SELECT id, ts_unix, probe, ok, latency_ms, detail
                FROM metrics
                ORDER BY id DESC
                LIMIT ?;
                ''',
                (limit,),
            )
            rows = []
            for _id, ts_unix, probe, ok, latency_ms, detail in cur.fetchall():
                rows.append(
                    {
                        "id": int(_id),
                        "ts_unix": ts_unix,
                        "probe": probe,
                        "ok": int(ok),
                        "latency_ms": latency_ms,
                        "detail": detail,
                    }
                )
            return rows


    def fetch_latest_alerts(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            cur = conn.execute(
                '''
                SELECT ts_unix, probe, severity, title, message
                FROM alerts
                ORDER BY ts_unix DESC
                LIMIT ?;
                ''',
                (limit,),
            )
            rows = []
            for ts_unix, probe, severity, title, message in cur.fetchall():
                rows.append(
                    {
                        "ts_unix": ts_unix,
                        "probe": probe,
                        "severity": severity,
                        "title": title,
                        "message": message,
                    }
                )
            return rows
        
    def get_last_sent_ts(self, dedup_key: str) -> int | None:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT last_sent_ts FROM alert_state WHERE dedup_key = ?;",
                (dedup_key,),
            )
            row = cur.fetchone()
            return int(row[0]) if row else None

    def upsert_last_sent_ts(self, dedup_key: str, ts_unix: int) -> None:
        with self._connect() as conn:
            conn.execute(
                '''
                INSERT INTO alert_state (dedup_key, last_sent_ts)
                VALUES (?, ?)
                ON CONFLICT(dedup_key) DO UPDATE SET last_sent_ts=excluded.last_sent_ts;
                ''',
                (dedup_key, ts_unix),
            )
            conn.commit()

    def fetch_metrics_by_probe(self, probe: str, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as conn:
            cur = conn.execute(
                '''
                SELECT ts_unix, probe, ok, latency_ms, detail
                FROM metrics
                WHERE probe = ?
                ORDER BY ts_unix DESC
                LIMIT ?;
                ''',
                (probe, limit),
            )
            rows = []
            for ts_unix, probe, ok, latency_ms, detail in cur.fetchall():
                rows.append(
                    {"ts_unix": ts_unix, "probe": probe, "ok": int(ok), "latency_ms": latency_ms, "detail": detail}
                )
            return rows
