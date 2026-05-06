from __future__ import annotations

from pathlib import Path

import pandas as pd

from research.schemas.domain_report import DomainReport, clamp01, normalize_action, parse_json_cell, safe_float


def load_weather_reports(
    signals_csv: Path | str | None = None,
    trades_csv: Path | str | None = None,
    signal_table_csv: Path | str | None = None,
    method: str = "proposed_agent",
) -> list[DomainReport]:
    if signals_csv and Path(signals_csv).exists():
        return _reports_from_unified_signals(Path(signals_csv), method=method)
    if signal_table_csv and Path(signal_table_csv).exists():
        return _reports_from_signal_table(Path(signal_table_csv), method=method)
    if trades_csv and Path(trades_csv).exists():
        return _reports_from_trades(Path(trades_csv), method=method)
    raise FileNotFoundError("Expected Weather signals_csv, signal_table_csv, or trades_csv to exist")


def _reports_from_unified_signals(path: Path, method: str) -> list[DomainReport]:
    frame = pd.read_csv(path)
    reports: list[DomainReport] = []
    for _, row in frame.iterrows():
        metadata = parse_json_cell(row.get("metadata"), default={})
        target = str(row.get("target", ""))
        reports.append(
            DomainReport(
                method=method,
                domain="weather",
                timestamp=str(row.get("timestamp", "")),
                market_id=str(row.get("market_id", "")),
                target=target,
                market_prob=clamp01(safe_float(row.get("market_prob"), 0.5)),
                model_prob=clamp01(safe_float(row.get("model_prob"), 0.5)),
                data_score=clamp01(safe_float(row.get("data_score"), 0.0)),
                news_score=clamp01(safe_float(row.get("news_score"), 0.0)),
                edge=abs(safe_float(row.get("edge"))),
                action=_normalize_unified_weather_action(row.get("action"), target, metadata),
                outcome=_text_or_blank(row.get("outcome")),
                evidence_ref=_text_or_blank(row.get("evidence_ref")) or str(path),
                pnl=_optional_float(row.get("pnl")),
                metadata={
                    "source": "Weather",
                    "signals_csv": str(path),
                    "source_method": row.get("method", ""),
                    "raw_action": row.get("action", ""),
                    "raw_metadata": metadata,
                },
            )
        )
    return reports


def _reports_from_trades(path: Path, method: str) -> list[DomainReport]:
    frame = pd.read_csv(path)
    reports: list[DomainReport] = []
    for _, row in frame.iterrows():
        action = normalize_action(row.get("side"))
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
                outcome=str(row.get("result", "")),
                evidence_ref=str(path),
                pnl=safe_float(row.get("pnl"), 0.0),
                metadata={
                    "source": "Weather",
                    "trades_csv": str(path),
                    "outcome_label": row.get("outcome_label", ""),
                    "forecast_max_temp_c": safe_float(row.get("forecast_max_temp_c")),
                    "sigma_c": safe_float(row.get("sigma_c")),
                },
            )
        )
    return reports


def _reports_from_signal_table(path: Path, method: str) -> list[DomainReport]:
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
                edge=abs(safe_float(row.get("best_edge"), model_prob - market_prob)),
                action=action,
                evidence_ref=str(path),
                metadata={
                    "source": "Weather",
                    "signal_table_csv": str(path),
                    "outcome_label": row.get("outcome_label", ""),
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


def _text_or_blank(value: object) -> str:
    text = str(value or "").strip()
    return "" if text.lower() in {"nan", "none"} else text


def _optional_float(value: object) -> float | None:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    return safe_float(value)
