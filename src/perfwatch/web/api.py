from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

from perfwatch.config import Config
from perfwatch.storage.sqlite import SQLiteStore
from perfwatch.utils.logging import get_logger

log = get_logger(__name__)


def _extract_ai_text(alert_message: str) -> str:
    """Extract AI analysis text from alert.message.

    Expected marker format in alert.message:
      ...\n\n---\nAI分析（DeepSeek）:\n<content>

    If marker is not found, returns empty string.
    """
    if not alert_message:
        return ""
    marker = "AI分析（DeepSeek）:"
    idx = alert_message.find(marker)
    if idx < 0:
        return ""
    return alert_message[idx + len(marker):].strip()


_HTML_DASHBOARD = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>PerfWatch Dashboard</title>

  <!-- Chart.js (CDN) -->
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>

  <style>
    body { font-family: Arial, sans-serif; margin: 16px; }
    h1 { margin: 0 0 8px 0; font-size: 20px; }
    .row { display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
    .card { border: 1px solid #ddd; border-radius: 8px; padding: 12px; }
    #chartWrap { width: 100%; max-width: 1200px; }
    table { border-collapse: collapse; width: 100%; max-width: 1200px; }
    th, td { border: 1px solid #ddd; padding: 8px; font-size: 12px; vertical-align: top; }
    th { background: #f6f6f6; text-align: left; position: sticky; top: 0; }
    .ok { color: #0a7; font-weight: 600; }
    .bad { color: #c00; font-weight: 700; }
    .muted { color: #666; }
    .small { font-size: 12px; }
    .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; }
    .pre { white-space: pre-wrap; word-break: break-word; }
  </style>
</head>

<body>
  <h1>PerfWatch Dashboard</h1>

  <div class="row controls small muted">
    <div>Auto refresh: <span id="refreshMsLabel"></span> ms</div>
    <div>Window: <span id="windowSecLabel"></span> sec</div>
    <div>Metrics table max rows: <span id="tableMaxLabel"></span></div>
    <div>AI table max rows: <span id="aiTableMaxLabel"></span></div>
  </div>

  <div class="card" id="chartWrap">
    <canvas id="latChart"></canvas>
  </div>

  <!-- Metrics table (no AI column) -->
  <div class="card" style="margin-top: 12px;">
    <div class="row" style="justify-content: space-between;">
      <div class="small muted">Latest metrics (new rows append over time)</div>
      <div class="small muted">Last seen metric id: <span id="lastMetricId">0</span></div>
    </div>

    <div style="overflow:auto; max-height: 420px; margin-top: 8px;">
      <table id="metricsTable">
        <thead>
          <tr>
            <th>ID</th>
            <th>Time</th>
            <th>Probe</th>
            <th>OK</th>
            <th>Latency (ms)</th>
            <th>Detail</th>
          </tr>
        </thead>
        <tbody id="metricsBody"></tbody>
      </table>
    </div>
  </div>

  <!-- AI Alerts table -->
  <div class="card" style="margin-top: 12px;">
    <div class="row" style="justify-content: space-between;">
      <div class="small muted">AI analysis entries (from /alerts; only rows containing the AI marker)</div>
      <div class="small muted">AI rows: <span id="aiRows">0</span></div>
    </div>

    <div style="overflow:auto; max-height: 520px; margin-top: 8px;">
      <table id="aiTable">
        <thead>
          <tr>
            <th>Time</th>
            <th>Probe</th>
            <th>Severity</th>
            <th>Title</th>
            <th>AI分析</th>
          </tr>
        </thead>
        <tbody id="aiBody"></tbody>
      </table>
    </div>
  </div>

<script>
(function(){
  const REFRESH_MS = 2000;
  const WINDOW_SEC = 10 * 60;
  const METRICS_FETCH_LIMIT = 300;
  const METRICS_TABLE_MAX_ROWS = 1000;

  const ALERTS_FETCH_LIMIT = 100;
  const AI_TABLE_MAX_ROWS = 200;

  document.getElementById("refreshMsLabel").textContent = REFRESH_MS;
  document.getElementById("windowSecLabel").textContent = WINDOW_SEC;
  document.getElementById("tableMaxLabel").textContent = METRICS_TABLE_MAX_ROWS;
  document.getElementById("aiTableMaxLabel").textContent = AI_TABLE_MAX_ROWS;

  let lastMetricId = 0;

  // probe -> [{x: ts_ms, y: latency_ms}]
  const seriesByProbe = new Map();

  // dedup AI rows (keyed by ts/probe/title/sev)
  const seenAiKeys = new Set();

  function fmtTime(tsMs) {
    const d = new Date(tsMs);
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    const ss = String(d.getSeconds()).padStart(2, "0");
    return `${hh}:${mm}:${ss}`;
  }

  function escapeHtml(s) {
    if (s === null || s === undefined) return "";
    return String(s)
      .replaceAll("&","&amp;")
      .replaceAll("<","&lt;")
      .replaceAll(">","&gt;")
      .replaceAll('"',"&quot;")
      .replaceAll("'","&#039;");
  }

  function extractAiTextFromMessage(msg) {
    if (!msg) return "";
    const marker = "AI分析（DeepSeek）:";
    const idx = String(msg).indexOf(marker);
    if (idx < 0) return "";
    return String(msg).slice(idx + marker.length).trim();
  }

  // ===== Chart init (NO time scale, use linear timestamp) =====
  let chart = null;
  if (typeof Chart !== "undefined") {
    const ctx = document.getElementById("latChart");
    chart = new Chart(ctx, {
      type: "line",
      data: { datasets: [] },
      options: {
        responsive: true,
        animation: false,
        parsing: false,
        scales: {
          x: {
            type: "linear",
            ticks: { callback: (value) => fmtTime(Number(value)) }
          },
          y: {
            title: { display: true, text: "Latency (ms)" },
            beginAtZero: true
          }
        },
        plugins: { legend: { display: true } }
      }
    });
  } else {
    console.warn("Chart.js not loaded; table will still work.");
  }

  function appendMetricRow(m) {
    const tbody = document.getElementById("metricsBody");
    const tsMs = m.ts_unix * 1000;
    const timeStr = new Date(tsMs).toLocaleString();

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${m.id}</td>
      <td>${escapeHtml(timeStr)}</td>
      <td>${escapeHtml(m.probe)}</td>
      <td class="${m.ok ? 'ok' : 'bad'}">${m.ok ? "OK" : "FAIL"}</td>
      <td>${m.latency_ms === null || m.latency_ms === undefined ? "" : Number(m.latency_ms).toFixed(1)}</td>
      <td class="muted">${escapeHtml(m.detail || "")}</td>
    `;
    tbody.appendChild(tr);

    while (tbody.children.length > METRICS_TABLE_MAX_ROWS) {
      tbody.removeChild(tbody.firstChild);
    }
  }

  function upsertChartPoint(m) {
    if (!chart) return;
    if (!m.ok) return;
    if (m.latency_ms === null || m.latency_ms === undefined) return;

    const probe = m.probe;
    const arr = seriesByProbe.get(probe) || [];
    const tsMs = m.ts_unix * 1000;

    arr.push({ x: tsMs, y: Number(m.latency_ms) });
    seriesByProbe.set(probe, arr);

    const cutoff = Date.now() - WINDOW_SEC * 1000;
    while (arr.length > 0 && arr[0].x < cutoff) arr.shift();
  }

  function rebuildDatasets() {
    if (!chart) return;

    const cutoff = Date.now() - WINDOW_SEC * 1000;
    for (const arr of seriesByProbe.values()) {
      while (arr.length > 0 && arr[0].x < cutoff) arr.shift();
    }

    const datasets = [];
    for (const [probe, arr] of seriesByProbe.entries()) {
      datasets.push({ label: probe, data: arr });
    }
    chart.data.datasets = datasets;

    chart.options.scales.x.min = cutoff;
    chart.options.scales.x.max = Date.now();
    chart.update("none");
  }

  function appendAiAlertRow(a, aiText) {
    const tbody = document.getElementById("aiBody");
    const tsMs = a.ts_unix * 1000;
    const timeStr = new Date(tsMs).toLocaleString();

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${escapeHtml(timeStr)}</td>
      <td class="mono">${escapeHtml(a.probe || "")}</td>
      <td class="${a.severity === 'critical' ? 'bad' : 'ok'}">${escapeHtml(a.severity || "")}</td>
      <td>${escapeHtml(a.title || "")}</td>
      <td class="pre">${escapeHtml(aiText)}</td>
    `;
    tbody.appendChild(tr);

    while (tbody.children.length > AI_TABLE_MAX_ROWS) {
      tbody.removeChild(tbody.firstChild);
    }

    document.getElementById("aiRows").textContent = String(tbody.children.length);
  }

  async function tickMetrics() {
    try {
      const res = await fetch(`/metrics?limit=${METRICS_FETCH_LIMIT}`);
      if (!res.ok) throw new Error(`metrics HTTP ${res.status}`);
      const data = await res.json();
      const metrics = data.metrics || [];

      metrics.sort((a,b) => a.id - b.id);

      for (const m of metrics) {
        if (m.id > lastMetricId) {
          appendMetricRow(m);
          upsertChartPoint(m);
          lastMetricId = m.id;
        }
      }

      document.getElementById("lastMetricId").textContent = String(lastMetricId);
      rebuildDatasets();
    } catch (e) {
      console.error("tickMetrics failed:", e);
    } finally {
      setTimeout(tickMetrics, REFRESH_MS);
    }
  }

  async function tickAlerts() {
    try {
      const res = await fetch(`/alerts?limit=${ALERTS_FETCH_LIMIT}`);
      if (!res.ok) throw new Error(`alerts HTTP ${res.status}`);
      const data = await res.json();
      const alerts = data.alerts || [];

      // newest last -> append in time order
      alerts.sort((a,b) => a.ts_unix - b.ts_unix);

      for (const a of alerts) {
        const aiText = extractAiTextFromMessage(a.message || "");
        if (!aiText) continue;

        const key = `${a.ts_unix}|${a.probe||""}|${a.severity||""}|${a.title||""}`;
        if (seenAiKeys.has(key)) continue;
        seenAiKeys.add(key);

        appendAiAlertRow(a, aiText);
      }
    } catch (e) {
      console.error("tickAlerts failed:", e);
    } finally {
      setTimeout(tickAlerts, REFRESH_MS);
    }
  }

  tickMetrics();
  tickAlerts();
})();
</script>

</body>
</html>
"""


class _Handler(BaseHTTPRequestHandler):
    cfg: Config = None  # type: ignore
    store: SQLiteStore = None  # type: ignore

    def _send_json(self, code: int, obj) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, code: int, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            return self._send_html(200, _HTML_DASHBOARD)

        if path == "/health":
            return self._send_json(200, {"ok": True})

        if path == "/rules":
            cfg = self.cfg
            rules = {
                "threshold_ms": {
                    "ping": {"warn": cfg.ping_latency_warn_ms, "critical": cfg.ping_latency_crit_ms},
                    "http": {"warn": cfg.http_latency_warn_ms, "critical": cfg.http_latency_crit_ms},
                },
                "collector": {
                    "ping_host": cfg.ping_host,
                    "ping_timeout_sec": cfg.ping_timeout_sec,
                    "http_url": cfg.http_url,
                    "http_timeout_sec": cfg.http_timeout_sec,
                },
                "runtime": {"interval_sec": cfg.interval_sec},
            }
            return self._send_json(200, {"rules": rules})

        if path == "/metrics":
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", ["200"])[0])
            probe = qs.get("probe", [None])[0]
            if probe:
                rows = self.store.fetch_metrics_by_probe(probe=probe, limit=limit)
            else:
                rows = self.store.fetch_latest_metrics(limit=limit)
            return self._send_json(200, {"metrics": rows})

        if path == "/alerts":
            qs = parse_qs(parsed.query)
            limit = int(qs.get("limit", ["50"])[0])
            rows = self.store.fetch_latest_alerts(limit=limit)
            return self._send_json(200, {"alerts": rows})

        return self._send_json(404, {"error": "not found", "path": path})

    def log_message(self, fmt, *args):
        log.info("web: " + fmt, *args)


def start_web_server(cfg: Config, store: SQLiteStore) -> None:
    _Handler.cfg = cfg
    _Handler.store = store

    server = HTTPServer((cfg.web_host, cfg.web_port), _Handler)
    log.info("Web server started on %s:%d", cfg.web_host, cfg.web_port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
