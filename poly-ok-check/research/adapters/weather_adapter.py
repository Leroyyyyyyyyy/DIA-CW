from __future__ import annotations

from pathlib import Path

import pandas as pd

from research.evaluation.outcomes import selected_side_outcome, weather_yes_outcome
from research.schemas.domain_report import DomainReport, clamp01, normalize_action, parse_json_cell, safe_float


def load_weather_reports(
    signals_csv: Path | str | None = None,
    trades_csv: Path | str | None = None,
    signal_table_csv: Path | str | None = None,
    method: str = "proposed_agent",
    actual_outcomes: dict[str, str] | None = None,
) -> list[DomainReport]:
    if signals_csv and Path(signals_csv).exists():
        return _reports_from_unified_signals(Path(signals_csv), method=method, actual_outcomes=actual_outcomes or {})
    if signal_table_csv and Path(signal_table_csv).exists():
        return _reports_from_signal_table(Path(signal_table_csv), method=method, actual_outcomes=actual_outcomes or {})
    if trades_csv and Path(trades_csv).exists():
        return _reports_from_trades(Path(trades_csv), method=method, actual_outcomes=actual_outcomes or {})
    raise FileNotFoundError("Expected Weather signals_csv, signal_table_csv, or trades_csv to exist")


def _reports_from_unified_signals(path: Path, method: str, actual_outcomes: dict[str, str]) -> list[DomainReport]:
    frame = pd.read_csv(path)
    reports: list[DomainReport] = []
    for _, row in frame.iterrows():
        metadata = parse_json_cell(row.get("metadata"), default={})
        target = str(row.get("target", ""))
        market_id = str(row.get("market_id", ""))
        action = _normalize_unified_weather_action(row.get("action"), target, metadata)
        candidate_side = _weather_candidate_side(action, target, metadata)
        market_label = _weather_label_from_target(target) or _weather_label_from_market_id(market_id, metadata)
        actual_label = _actual_weather_label(market_id, metadata, actual_outcomes)
        yes_outcome = weather_yes_outcome(market_label, actual_label)
        outcome = selected_side_outcome(action, yes_outcome) or _text_or_blank(row.get("outcome"))
        reports.append(
            DomainReport(
                method=method,
                domain="weather",
                timestamp=str(row.get("timestamp", "")),
                market_id=market_id,
                target=target,
                market_prob=clamp01(safe_float(row.get("market_prob"), 0.5)),
                model_prob=clamp01(safe_float(row.get("model_prob"), 0.5)),
                data_score=clamp01(safe_float(row.get("data_score"), 0.0)),
                news_score=clamp01(safe_float(row.get("news_score"), 0.0)),
                edge=abs(safe_float(row.get("edge"))),
                action=action,
                outcome=outcome,
                evidence_ref=_text_or_blank(row.get("evidence_ref")) or str(path),
                pnl=None,
                metadata={
                    "source": "Weather",
                    "signals_csv": str(path),
                    "source_method": row.get("method", ""),
                    "candidate_side": candidate_side,
                    "market_label": market_label,
                    "actual_outcome_label": actual_label,
                    "yes_outcome": yes_outcome,
                    "raw_action": row.get("action", ""),
                    "raw_pnl": _optional_float(row.get("pnl")),
                    "raw_metadata": metadata,
                },
            )
        )
    return reports


def _reports_from_trades(path: Path, method: str, actual_outcomes: dict[str, str]) -> list[DomainReport]:
    frame = pd.read_csv(path)
    reports: list[DomainReport] = []
    for _, row in frame.iterrows():
        action = normalize_action(row.get("side"))
        market_id = str(row.get("market_slug", ""))
        metadata = {"event_slug": _event_slug_from_market_id(market_id)}
        market_label = str(row.get("outcome_label", ""))
        actual_label = _actual_weather_label(market_id, metadata, actual_outcomes)
        yes_outcome = weather_yes_outcome(market_label, actual_label)
        outcome = selected_side_outcome(action, yes_outcome) or str(row.get("result", ""))
        market_prob = clamp01(safe_float(row.get("entry_price"), 0.5))
        model_prob = clamp01(safe_float(row.get("model_prob"), 0.5))
        edge = abs(safe_float(row.get("edge"), model_prob - market_prob))
        reports.append(
            DomainReport(
                method=method,
                domain="weather",
                timestamp=str(row.get("timestamp_utc", "")),
                market_id=str(row.get("market_slug", "")),
                target=f"Weather {row.get('target_date', '')} {row.get('outcome_label', '')}".strip(),
                market_prob=market_prob,
                model_prob=model_prob,
                data_score=model_prob,
                news_score=0.0,
                edge=edge,
                action=action,
                outcome=outcome,
                evidence_ref=str(path),
                pnl=None,
                metadata={
                    "source": "Weather",
                    "trades_csv": str(path),
                    "candidate_side": action,
                    "outcome_label": row.get("outcome_label", ""),
                    "actual_outcome_label": actual_label,
                    "yes_outcome": yes_outcome,
                    "forecast_max_temp_c": safe_float(row.get("forecast_max_temp_c")),
                    "sigma_c": safe_float(row.get("sigma_c")),
                    "raw_pnl": safe_float(row.get("pnl"), 0.0),
                },
            )
        )
    return reports


def _reports_from_signal_table(path: Path, method: str, actual_outcomes: dict[str, str]) -> list[DomainReport]:
    frame = pd.read_csv(path)
    reports: list[DomainReport] = []
    for _, row in frame.iterrows():
        action = normalize_action(row.get("signal"))
        if action == "YES":
            market_prob = clamp01(safe_float(row.get("yes_price"), 0.5))
            model_prob = clamp01(safe_float(row.get("model_prob_yes"), 0.5))
        elif action == "NO":
            market_prob = clamp01(safe_float(row.get("no_price"), 0.5))
            model_prob = clamp01(safe_float(row.get("model_prob_no"), 0.5))
        else:
            market_prob = clamp01(safe_float(row.get("yes_price"), 0.5))
            model_prob = clamp01(safe_float(row.get("model_prob_yes"), 0.5))
        market_id = str(row.get("market_slug", ""))
        market_label = str(row.get("outcome_label", ""))
        actual_label = _actual_weather_label(market_id, {"event_slug": row.get("event_slug", "")}, actual_outcomes)
        yes_outcome = weather_yes_outcome(market_label, actual_label)
        reports.append(
            DomainReport(
                method=method,
                domain="weather",
                timestamp=str(row.get("timestamp_utc", "")),
                market_id=market_id,
                target=f"Weather {row.get('target_date', '')} {row.get('outcome_label', '')}".strip(),
                market_prob=market_prob,
                model_prob=model_prob,
                data_score=model_prob,
                news_score=0.0,
                edge=abs(safe_float(row.get("best_edge"), model_prob - market_prob)),
                action=action,
                outcome=selected_side_outcome(action, yes_outcome),
                evidence_ref=str(path),
                metadata={
                    "source": "Weather",
                    "signal_table_csv": str(path),
                    "candidate_side": _candidate_side_from_signal(action, row),
                    "outcome_label": row.get("outcome_label", ""),
                    "actual_outcome_label": actual_label,
                    "yes_outcome": yes_outcome,
                    "raw_signal": row.get("signal", ""),
                },
            )
        )
    return reports


def _normalize_unified_weather_action(value: object, target: str, metadata: dict) -> str:
    action = str(value or "").strip().upper()
    if action == "ENTER":
        side = str(metadata.get("side") or _side_from_target(target)).strip().upper()
        return normalize_action(side)
    return normalize_action(action)


def _side_from_target(target: str) -> str:
    text = target.strip().upper()
    if text.endswith(" YES"):
        return "YES"
    if text.endswith(" NO"):
        return "NO"
    return ""


def _weather_candidate_side(action: str, target: str, metadata: dict) -> str:
    side = normalize_action(action)
    if side in {"YES", "NO"}:
        return side
    metadata_side = normalize_action(metadata.get("side"))
    if metadata_side in {"YES", "NO"}:
        return metadata_side
    target_side = normalize_action(_side_from_target(target))
    return target_side if target_side in {"YES", "NO"} else "YES"


def _candidate_side_from_signal(action: str, row: pd.Series) -> str:
    side = normalize_action(action)
    if side in {"YES", "NO"}:
        return side
    yes_edge = safe_float(row.get("yes_edge"))
    no_edge = safe_float(row.get("no_edge"))
    return "YES" if yes_edge >= no_edge else "NO"


def _actual_weather_label(market_id: str, metadata: dict, actual_outcomes: dict[str, str]) -> str:
    event_slug = str(metadata.get("event_slug") or _event_slug_from_market_id(market_id)).strip()
    return str(actual_outcomes.get(event_slug) or actual_outcomes.get(market_id) or "")


def _event_slug_from_market_id(market_id: str) -> str:
    slug = str(market_id or "")
    if not slug:
        return ""
    parts = slug.rsplit("-", 1)
    return parts[0] if len(parts) == 2 else slug


def _weather_label_from_target(target: str) -> str:
    text = str(target or "").strip()
    upper = text.upper()
    if upper.endswith(" YES") or upper.endswith(" NO"):
        return text.rsplit(" ", 1)[0].strip()
    return text


def _weather_label_from_market_id(market_id: str, metadata: dict) -> str:
    event_slug = str(metadata.get("event_slug") or _event_slug_from_market_id(market_id)).strip()
    text = str(market_id or "")
    prefix = f"{event_slug}-" if event_slug else ""
    return text[len(prefix) :] if prefix and text.startswith(prefix) else text


def _text_or_blank(value: object) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"nan", "none"} else text


def _optional_float(value: object) -> float | None:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    return safe_float(value)
