from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

from perfwatch.config import Config
from perfwatch.rules.base import Rule
from perfwatch.rules.threshold import PrefixThresholdRule, ThresholdRule
from perfwatch.rules.baseline import BaselineRule
from perfwatch.utils.logging import get_logger

log = get_logger(__name__)


def _as_float(x, default: float) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _as_int(x, default: int) -> int:
    try:
        return int(x)
    except Exception:
        return default


def load_rules_from_yaml(path: str) -> list[Rule]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))

    with p.open("r", encoding="utf-8") as f:
        doc = yaml.safe_load(f)

    if not isinstance(doc, dict):
        raise ValueError("rules.yaml must be a mapping at top level")

    rules_raw = doc.get("rules", [])
    if not isinstance(rules_raw, list):
        raise ValueError("rules must be a list")

    rules: list[Rule] = []

    for i, r in enumerate(rules_raw):
        if not isinstance(r, dict):
            log.warning("Skipping rule #%d: not a mapping", i)
            continue

        typ = str(r.get("type", "")).strip().lower()
        prefix = str(r.get("probe_prefix", "")).strip()
        if not prefix:
            log.warning("Skipping rule #%d: missing probe_prefix", i)
            continue

        if typ == "threshold":
            warn_ms = _as_float(r.get("warn_ms"), 0.0)
            crit_ms = _as_float(r.get("crit_ms"), 0.0)
            if warn_ms <= 0 or crit_ms <= 0 or crit_ms < warn_ms:
                log.warning("Skipping threshold rule #%d: invalid warn/crit", i)
                continue
            rules.append(PrefixThresholdRule(probe_prefix=prefix, warn_ms=warn_ms, crit_ms=crit_ms))

        elif typ == "baseline":
            window_size = _as_int(r.get("window_size"), 50)
            method = str(r.get("method", "p90")).strip().lower()
            factor_warn = _as_float(r.get("factor_warn"), 2.0)
            factor_crit = _as_float(r.get("factor_crit"), 3.0)
            min_baseline_ms = _as_float(r.get("min_baseline_ms"), 0.0)

            if window_size <= 0 or factor_warn <= 0 or factor_crit <= 0 or factor_crit < factor_warn:
                log.warning("Skipping baseline rule #%d: invalid window/factors", i)
                continue

            rules.append(
                BaselineRule(
                    probe_prefix=prefix,
                    window_size=window_size,
                    method=method,
                    factor_warn=factor_warn,
                    factor_crit=factor_crit,
                    min_baseline_ms=min_baseline_ms,
                )
            )
        else:
            log.warning("Skipping rule #%d: unknown type=%s", i, typ)

    return rules


@dataclass
class RulesManager:
    """
    Keeps a live set of rules loaded from rules.yaml and reloads on change.
    If loading fails, it keeps last known-good rules.
    """
    rules_path: str
    reload_sec: int
    rules: list[Rule]
    _last_mtime: float = 0.0
    _last_check_monotonic: float = 0.0

    @staticmethod
    def from_config(cfg: Config) -> "RulesManager":
        # initial rules:
        # 1) try YAML
        # 2) fallback to env-based ThresholdRule (so the system can still run)
        rules: list[Rule]
        try:
            rules = load_rules_from_yaml(cfg.rules_path)
            log.info("Loaded %d rule(s) from %s", len(rules), cfg.rules_path)
        except Exception as e:
            log.warning("Failed to load rules from %s (%s). Falling back to env thresholds.", cfg.rules_path, e)
            rules = [ThresholdRule.from_config(cfg)]

        mgr = RulesManager(
            rules_path=cfg.rules_path,
            reload_sec=max(1, int(cfg.rules_reload_sec)),
            rules=rules,
        )
        mgr._last_mtime = mgr._get_mtime_or_zero()
        mgr._last_check_monotonic = time.monotonic()
        return mgr

    def _get_mtime_or_zero(self) -> float:
        try:
            return os.path.getmtime(self.rules_path)
        except Exception:
            return 0.0

    def refresh_if_needed(self) -> None:
        now = time.monotonic()
        if now - self._last_check_monotonic < float(self.reload_sec):
            return
        self._last_check_monotonic = now

        mtime = self._get_mtime_or_zero()
        if mtime <= 0 or mtime == self._last_mtime:
            return

        try:
            new_rules = load_rules_from_yaml(self.rules_path)
            if not new_rules:
                log.warning("Reloaded rules.yaml but got 0 rules; keeping existing rules.")
                self._last_mtime = mtime
                return

            self.rules = new_rules
            self._last_mtime = mtime
            log.info("Rules reloaded: %d rule(s) from %s", len(self.rules), self.rules_path)
        except Exception as e:
            log.warning("Rules reload failed (%s). Keeping existing rules.", e)
            self._last_mtime = mtime  # avoid spamming reload attempts on same bad file
