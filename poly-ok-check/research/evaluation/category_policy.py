from __future__ import annotations

import csv
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Any

from research.schemas.domain_report import DomainReport, normalize_action, safe_float


POLICY_DIAGNOSTIC_FIELDS = [
    "domain",
    "timestamp",
    "market_id",
    "target",
    "original_action",
    "policy_action",
    "reason",
    "edge",
    "news_score",
]


def apply_category_policy(
    reports: list[DomainReport],
    policy: dict[str, Any] | None,
    inputs: dict[str, Any] | None = None,
    base_dir: Path | None = None,
    config_dir: Path | None = None,
) -> tuple[list[DomainReport], list[dict[str, Any]]]:
    if not policy or not policy.get("enabled", False):
        return list(reports), []

    base = base_dir or Path.cwd()
    config_base = config_dir or base
    input_config = inputs or {}

    current: dict[int, DomainReport | None] = {index: report for index, report in enumerate(reports)}
    diagnostics: list[dict[str, Any]] = []

    _apply_weather_policy(current, policy.get("weather", {}), input_config.get("weather", {}), base, config_base, diagnostics)
    _apply_btc_policy(current, policy.get("btc", {}), diagnostics)
    _apply_cs2_policy(current, policy.get("cs2", {}), diagnostics)

    adjusted = [report for index, report in sorted(current.items()) if report is not None]
    return adjusted, diagnostics


def write_policy_diagnostics(rows: list[dict[str, Any]], path: Path | str) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=POLICY_DIAGNOSTIC_FIELDS)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in POLICY_DIAGNOSTIC_FIELDS} for row in rows)
    return out


def _apply_weather_policy(
    current: dict[int, DomainReport | None],
    policy: dict[str, Any],
    inputs: dict[str, Any],
    base_dir: Path,
    config_dir: Path,
    diagnostics: list[dict[str, Any]],
) -> None:
    if not policy or policy.get("execution_source") != "trades_csv":
        return

    trades_path = _resolve_optional(policy.get("trades_csv") or inputs.get("trades_csv"), base_dir, config_dir)
    trade_keys = _load_weather_trade_keys(trades_path) if trades_path else set()
    accepted_keys, acceptance_reasons = _weather_accepted_keys(current, trade_keys, policy)
    max_per_event = int(policy.get("max_trades_per_event", 0) or 0)
    max_per_market_side = int(policy.get("max_trades_per_market_side", 0) or 0)
    event_counts: Counter[str] = Counter()
    market_side_counts: Counter[tuple[str, str]] = Counter()

    for index, report in list(current.items()):
        if report is None or report.domain.lower() != "weather":
            continue

        action = normalize_action(report.action)
        if not trade_keys:
            current[index] = None
            diagnostics.append(_diagnostic(report, "DROP", "weather_trades_csv_missing"))
            continue

        key = _weather_report_trade_key(report, action)
        if key not in accepted_keys:
            current[index] = None
            diagnostics.append(_diagnostic(report, "DROP", "weather_execution_not_selected"))
            continue

        event_slug = _event_slug(report)
        market_side = (report.market_id, action)
        if max_per_market_side > 0 and market_side_counts[market_side] >= max_per_market_side:
            current[index] = None
            diagnostics.append(_diagnostic(report, "DROP", "weather_market_side_trade_limit"))
            continue
        if max_per_event > 0 and event_counts[event_slug] >= max_per_event:
            current[index] = None
            diagnostics.append(_diagnostic(report, "DROP", "weather_event_trade_limit"))
            continue

        event_counts[event_slug] += 1
        market_side_counts[market_side] += 1
        reason = acceptance_reasons.get(key, "weather_execution_in_trades")
        current[index] = _with_policy_metadata(
            report,
            policy_action=action,
            reason=reason,
            blocked=False,
        )
        diagnostics.append(_diagnostic(report, action, reason))


def _weather_accepted_keys(
    current: dict[int, DomainReport | None],
    trade_keys: set[tuple[str, str, str]],
    policy: dict[str, Any],
) -> tuple[set[tuple[str, str, str]], dict[tuple[str, str, str], str]]:
    accepted: set[tuple[str, str, str]] = set()
    reasons: dict[tuple[str, str, str], str] = {}
    event_counts: Counter[str] = Counter()
    market_side_counts: Counter[tuple[str, str]] = Counter()
    max_per_event = int(policy.get("max_trades_per_event", 0) or 0)
    max_per_market_side = int(policy.get("max_trades_per_market_side", 0) or 0)

    reports = [
        report
        for report in current.values()
        if report is not None and report.domain.lower() == "weather" and normalize_action(report.action) in {"YES", "NO"}
    ]
    reports.sort(key=lambda report: report.timestamp)
    for report in reports:
        action = normalize_action(report.action)
        key = _weather_report_trade_key(report, action)
        if key not in trade_keys:
            continue
        if _weather_policy_limit_hit(report, action, event_counts, market_side_counts, max_per_event, max_per_market_side):
            continue
        accepted.add(key)
        reasons[key] = "weather_execution_in_trades"
        event_counts[_event_slug(report)] += 1
        market_side_counts[(report.market_id, action)] += 1

    backfill = policy.get("candidate_backfill", {})
    if not backfill or not backfill.get("enabled", False):
        return accepted, reasons

    max_total = int(backfill.get("max_total_trades", max_per_event) or 0)
    min_edge = float(backfill.get("min_edge", 0.0) or 0.0)
    min_news_score = float(backfill.get("min_news_score", 0.0) or 0.0)
    candidates = sorted(
        reports,
        key=lambda report: (safe_float(report.edge), safe_float(report.news_score), report.timestamp),
        reverse=True,
    )
    for report in candidates:
        if max_total > 0 and len(accepted) >= max_total:
            break
        action = normalize_action(report.action)
        key = _weather_report_trade_key(report, action)
        if key in accepted or key in trade_keys:
            continue
        if safe_float(report.edge) < min_edge or safe_float(report.news_score) < min_news_score:
            continue
        if _weather_policy_limit_hit(report, action, event_counts, market_side_counts, max_per_event, max_per_market_side):
            continue
        accepted.add(key)
        reasons[key] = "weather_candidate_backfill"
        event_counts[_event_slug(report)] += 1
        market_side_counts[(report.market_id, action)] += 1

    return accepted, reasons


def _weather_policy_limit_hit(
    report: DomainReport,
    action: str,
    event_counts: Counter[str],
    market_side_counts: Counter[tuple[str, str]],
    max_per_event: int,
    max_per_market_side: int,
) -> bool:
    if max_per_event > 0 and event_counts[_event_slug(report)] >= max_per_event:
        return True
    if max_per_market_side > 0 and market_side_counts[(report.market_id, action)] >= max_per_market_side:
        return True
    return False


def _apply_btc_policy(
    current: dict[int, DomainReport | None],
    policy: dict[str, Any],
    diagnostics: list[dict[str, Any]],
) -> None:
    if not policy:
        return

    min_edge = float(policy.get("min_edge", 0.0) or 0.0)
    min_news_score = float(policy.get("min_news_score", 0.0) or 0.0)
    max_per_market = int(policy.get("max_trades_per_market", 0) or 0)
    market_counts: Counter[str] = Counter()

    for index, report in list(current.items()):
        if report is None or report.domain.lower() != "btc":
            continue

        action = normalize_action(report.action)
        if action not in {"YES", "NO"}:
            diagnostics.append(_diagnostic(report, action, "btc_non_entry_action"))
            continue

        if safe_float(report.edge) < min_edge:
            current[index] = _blocked_report(report, "btc_below_edge_threshold")
            diagnostics.append(_diagnostic(report, "HOLD", "btc_below_edge_threshold"))
            continue
        if safe_float(report.news_score) < min_news_score:
            current[index] = _blocked_report(report, "btc_below_news_threshold")
            diagnostics.append(_diagnostic(report, "HOLD", "btc_below_news_threshold"))
            continue
        if max_per_market > 0 and market_counts[report.market_id] >= max_per_market:
            current[index] = _blocked_report(report, "btc_market_trade_limit")
            diagnostics.append(_diagnostic(report, "HOLD", "btc_market_trade_limit"))
            continue

        market_counts[report.market_id] += 1
        current[index] = _with_policy_metadata(report, policy_action=action, reason="btc_policy_pass", blocked=False)
        diagnostics.append(_diagnostic(report, action, "btc_policy_pass"))


def _apply_cs2_policy(
    current: dict[int, DomainReport | None],
    policy: dict[str, Any],
    diagnostics: list[dict[str, Any]],
) -> None:
    if not policy:
        return

    max_per_market_side = int(policy.get("max_trades_per_market_side", 0) or 0)
    switch_buffer = float(policy.get("switch_buffer", 0.0) or 0.0)
    side_counts: Counter[tuple[str, str]] = Counter()
    current_position: dict[str, tuple[str, float]] = {}

    cs2_items = [
        (index, report)
        for index, report in current.items()
        if report is not None and report.domain.lower() == "cs2"
    ]
    cs2_items.sort(key=lambda item: item[1].timestamp)

    for index, report in cs2_items:
        action = normalize_action(report.action)
        if action not in {"YES", "NO"}:
            diagnostics.append(_diagnostic(report, action, "cs2_non_entry_action"))
            continue

        edge = safe_float(report.edge)
        market_side = (report.market_id, action)
        if max_per_market_side > 0 and side_counts[market_side] >= max_per_market_side:
            current[index] = _blocked_report(report, "cs2_position_already_open")
            diagnostics.append(_diagnostic(report, "HOLD", "cs2_position_already_open"))
            continue

        prior = current_position.get(report.market_id)
        if prior is not None:
            prior_side, prior_edge = prior
            if prior_side != action and edge < prior_edge + switch_buffer:
                current[index] = _blocked_report(report, "cs2_switch_buffer_not_met")
                diagnostics.append(_diagnostic(report, "HOLD", "cs2_switch_buffer_not_met"))
                continue

        side_counts[market_side] += 1
        current_position[report.market_id] = (action, edge)
        current[index] = _with_policy_metadata(report, policy_action=action, reason="cs2_policy_pass", blocked=False)
        diagnostics.append(_diagnostic(report, action, "cs2_policy_pass"))


def _blocked_report(report: DomainReport, reason: str) -> DomainReport:
    return _with_policy_metadata(
        replace(report, action="HOLD", outcome="", pnl=None),
        policy_action="HOLD",
        reason=reason,
        blocked=True,
    )


def _with_policy_metadata(
    report: DomainReport,
    policy_action: str,
    reason: str,
    blocked: bool,
) -> DomainReport:
    metadata = dict(report.metadata)
    metadata.update(
        {
            "policy_action": policy_action,
            "policy_reason": reason,
            "policy_blocked": blocked,
        }
    )
    return replace(report, metadata=metadata)


def _diagnostic(report: DomainReport, policy_action: str, reason: str) -> dict[str, Any]:
    return {
        "domain": report.domain,
        "timestamp": report.timestamp,
        "market_id": report.market_id,
        "target": report.target,
        "original_action": normalize_action(report.action),
        "policy_action": policy_action,
        "reason": reason,
        "edge": report.edge,
        "news_score": report.news_score,
    }


def _load_weather_trade_keys(path: Path) -> set[tuple[str, str, str]]:
    keys: set[tuple[str, str, str]] = set()
    if not path.exists():
        return keys
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            action = normalize_action(row.get("side"))
            if action in {"YES", "NO"}:
                keys.add((_clean_text(row.get("timestamp_utc")), _clean_text(row.get("market_slug")), action))
    return keys


def _weather_report_trade_key(report: DomainReport, action: str) -> tuple[str, str, str]:
    return (_clean_text(report.timestamp), _clean_text(report.market_id), action)


def _event_slug(report: DomainReport) -> str:
    raw_metadata = report.metadata.get("raw_metadata")
    if isinstance(raw_metadata, dict):
        event_slug = _clean_text(raw_metadata.get("event_slug"))
        if event_slug:
            return event_slug
    market_id = _clean_text(report.market_id)
    parts = market_id.rsplit("-", 1)
    return parts[0] if len(parts) == 2 else market_id


def _resolve_optional(value: str | Path | None, base_dir: Path, config_dir: Path) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    from_base = base_dir / path
    if from_base.exists():
        return from_base
    return config_dir / path


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if not text or text.lower() in {"nan", "none"} else text
