from __future__ import annotations

import json

import pandas as pd

from research.adapters.acy_news_adapter import load_acy_news_reports
from research.adapters.cs2_adapter import load_cs2_reports
from research.adapters.weather_adapter import load_weather_reports


def test_acy_news_adapter_converts_signal_csv(tmp_path) -> None:
    path = tmp_path / "signals.csv"
    pd.DataFrame(
        [
            {
                "domain": "btc",
                "target": "BTC near-term",
                "direction_score": 0.2,
                "confidence": 0.8,
                "relevance": 0.5,
                "probability_delta": 0.04,
                "outcome_scores": json.dumps({"long": 0.2, "short": -0.2}),
                "top_evidence": json.dumps([{"title": "BTC evidence"}]),
                "generated_at": "2026-04-30T00:00:00Z",
                "metadata": json.dumps({"time_window": {"as_of": "2026-04-30T09:00:00+08:00"}}),
            }
        ]
    ).to_csv(path, index=False)

    reports = load_acy_news_reports(path, domains=["btc"])

    assert len(reports) == 1
    assert reports[0].domain == "btc"
    assert reports[0].model_prob == 0.54
    assert reports[0].evidence_ref == "BTC evidence"


def test_weather_adapter_prefers_unified_signal_rows(tmp_path) -> None:
    signals = tmp_path / "signals.csv"
    trades = tmp_path / "backtest_trades.csv"
    pd.DataFrame(
        [
            {
                "method": "weather_forecast_market_edge",
                "domain": "weather",
                "timestamp": "2026-04-30 00:00:00+0000",
                "market_id": "weather-market",
                "target": "18C NO",
                "market_prob": 0.6,
                "model_prob": 0.75,
                "data_score": 0.15,
                "news_score": 0.0,
                "edge": 0.15,
                "action": "enter",
                "outcome": "WIN",
                "evidence_ref": "weather_ev_1",
                "pnl": 0.5,
                "metadata": json.dumps({"side": "NO"}),
            }
        ]
    ).to_csv(signals, index=False)
    pd.DataFrame(
        [
            {
                "timestamp_utc": "2026-04-30 00:00:00+0000",
                "target_date": "2026-04-30",
                "outcome_label": "18C",
                "side": "NO",
                "entry_price": 0.6,
                "model_prob": 0.75,
                "edge": 0.15,
                "result": "WIN",
                "pnl": 0.5,
                "market_slug": "weather-market",
            }
        ]
    ).to_csv(trades, index=False)

    reports = load_weather_reports(signals_csv=signals, trades_csv=trades)

    assert len(reports) == 1
    assert reports[0].action == "NO"
    assert reports[0].pnl == 0.5


def test_cs2_adapter_uses_timeline_decisions(tmp_path) -> None:
    signals = tmp_path / "signals.csv"
    timeline = tmp_path / "timeline.csv"
    pd.DataFrame([{"timestamp_s": 10.0, "fair_prob": 0.7, "reason": "demo"}]).to_csv(signals, index=False)
    pd.DataFrame(
        [
            {
                "timestamp_s": 12.0,
                "decision_count": 1,
                "target_side": "YES",
                "orderbook_mid": 0.55,
                "market_id": "cs2-market",
            }
        ]
    ).to_csv(timeline, index=False)

    reports = load_cs2_reports(signals, timeline_csv=timeline, yes_outcome=1.0)

    assert len(reports) == 1
    assert reports[0].market_id == "cs2-market"
    assert reports[0].outcome == "WIN"
