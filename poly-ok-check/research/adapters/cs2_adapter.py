from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from research.schemas.domain_report import DomainReport, clamp01, infer_action, normalize_action, safe_float


def load_cs2_reports(
    signal_csv: Path | str,
    timeline_csv: Path | str | None = None,
    market_id: str = "cs2-run2-omega1-2026-04-03",
    target: str = "Rune Eaters vs Omega",
    yes_outcome: float | None = 1.0,
    market_prob_default: float = 0.5,
    method: str = "proposed_agent",
) -> list[DomainReport]:
    signals = pd.read_csv(signal_csv).sort_values("timestamp_s").reset_index(drop=True)
    if timeline_csv and Path(timeline_csv).exists():
        return _reports_from_timeline(
            signals=signals,
            timeline_path=Path(timeline_csv),
            market_id=market_id,
            target=target,
            yes_outcome=yes_outcome,
            method=method,
        )
    return _reports_from_signals(
        signals=signals,
        signal_path=Path(signal_csv),
        market_id=market_id,
        target=target,
        yes_outcome=yes_outcome,
        market_prob_default=market_prob_default,
        method=method,
    )


def _reports_from_timeline(
    signals: pd.DataFrame,
    timeline_path: Path,
    market_id: str,
    target: str,
    yes_outcome: float | None,
    method: str,
) -> list[DomainReport]:
    timeline = pd.read_csv(timeline_path)
    reports: list[DomainReport] = []
    decision_rows = timeline[timeline["decision_count"].fillna(0).astype(float) > 0]
    for _, row in decision_rows.iterrows():
        ts_s = safe_float(row.get("timestamp_s"))
        signal = _latest_signal(signals, ts_s)
        fair_prob_yes = clamp01(safe_float(signal.get("fair_prob"), 0.5)) if signal is not None else 0.5
        action = normalize_action(row.get("target_side"))
        mid_yes = clamp01(safe_float(row.get("orderbook_mid"), 0.5))
        market_prob = 1.0 - mid_yes if action == "NO" else mid_yes
        model_prob = 1.0 - fair_prob_yes if action == "NO" else fair_prob_yes
        reports.append(
            DomainReport(
                method=method,
                domain="cs2",
                timestamp=_ts_to_iso(ts_s),
                market_id=str(row.get("market_id") or market_id),
                target=target,
                market_prob=market_prob,
                model_prob=model_prob,
                data_score=model_prob,
                news_score=0.0,
                edge=abs(model_prob - market_prob),
                action=action,
                outcome=_selected_outcome(action, yes_outcome),
                evidence_ref=str(timeline_path),
                metadata={
                    "source": "poly-ok-check",
                    "timeline_csv": str(timeline_path),
                    "reason": str(signal.get("reason", "")) if signal is not None else "",
                    "fair_prob_yes": fair_prob_yes,
                    "orderbook_mid_yes": mid_yes,
                },
            )
        )
    return reports


def _reports_from_signals(
    signals: pd.DataFrame,
    signal_path: Path,
    market_id: str,
    target: str,
    yes_outcome: float | None,
    market_prob_default: float,
    method: str,
) -> list[DomainReport]:
    reports: list[DomainReport] = []
    for _, row in signals.iterrows():
        fair_prob = clamp01(safe_float(row.get("fair_prob"), 0.5))
        market_prob = clamp01(market_prob_default)
        action = infer_action(fair_prob, market_prob)
        model_prob = 1.0 - fair_prob if action == "NO" else fair_prob
        selected_market_prob = 1.0 - market_prob if action == "NO" else market_prob
        reports.append(
            DomainReport(
                method=method,
                domain="cs2",
                timestamp=_ts_to_iso(safe_float(row.get("timestamp_s"))),
                market_id=market_id,
                target=target,
                market_prob=selected_market_prob,
                model_prob=model_prob,
                data_score=model_prob,
                news_score=0.0,
                edge=abs(model_prob - selected_market_prob),
                action=action,
                outcome=_selected_outcome(action, yes_outcome),
                evidence_ref=str(signal_path),
                metadata={"source": "poly-ok-check", "reason": str(row.get("reason", ""))},
            )
        )
    return reports


def _latest_signal(signals: pd.DataFrame, ts_s: float) -> pd.Series | None:
    eligible = signals[signals["timestamp_s"].astype(float) <= ts_s]
    if eligible.empty:
        return None
    return eligible.iloc[-1]


def _selected_outcome(action: str, yes_outcome: float | None) -> str:
    if yes_outcome is None or action not in {"YES", "NO"}:
        return ""
    yes_won = float(yes_outcome) >= 0.5
    selected_won = yes_won if action == "YES" else not yes_won
    return "WIN" if selected_won else "LOSE"


def _ts_to_iso(ts_s: float) -> str:
    return datetime.fromtimestamp(ts_s, timezone.utc).isoformat().replace("+00:00", "Z")

