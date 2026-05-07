from __future__ import annotations

import json

import pandas as pd

from research.adapters.acy_news_adapter import load_acy_news_reports
from research.adapters.cs2_adapter import load_cs2_reports
from research.adapters.weather_adapter import load_weather_reports
from research.evaluation.outcomes import load_yes_outcomes_csv
from research.run.fetch_btc_5m_outcomes import build_btc_outcome_rows, write_btc_outcome_csv


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


def test_acy_news_adapter_uses_selected_side_probability_for_no(tmp_path) -> None:
    path = tmp_path / "signals.csv"
    outcome_path = tmp_path / "btc_outcome.csv"
    pd.DataFrame(
        [
            {
                "domain": "btc",
                "target": "BTC near-term",
                "direction_score": -0.2,
                "confidence": 0.8,
                "relevance": 0.5,
                "probability_delta": 0.04,
                "outcome_scores": json.dumps({"long": -0.2, "short": 0.2}),
                "top_evidence": json.dumps([{"title": "BTC evidence"}]),
                "generated_at": "2026-04-30T00:00:00Z",
                "metadata": json.dumps({"market_id": "btc_5m_up_down", "market_prob": 0.5}),
            }
        ]
    ).to_csv(path, index=False)
    pd.DataFrame([{"market_id": "btc_5m_up_down", "yes_outcome": 0.0}]).to_csv(outcome_path, index=False)

    reports = load_acy_news_reports(path, domains=["btc"], outcome_csv=outcome_path)

    assert reports[0].action == "NO"
    assert reports[0].model_prob == 0.54
    assert reports[0].market_prob == 0.5
    assert reports[0].outcome == "WIN"


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
    assert reports[0].metadata["raw_pnl"] == 0.5


def test_weather_adapter_resolves_actual_temperature_outcomes(tmp_path) -> None:
    signals = tmp_path / "signals.csv"
    pd.DataFrame(
        [
            {
                "method": "weather_forecast_market_edge",
                "domain": "weather",
                "timestamp": "2026-04-24 17:00:04+0000",
                "market_id": "highest-temperature-in-shanghai-on-april-25-2026-21c",
                "target": "21掳C NO",
                "market_prob": 0.675,
                "model_prob": 0.822,
                "data_score": 0.147,
                "news_score": 0.0,
                "edge": 0.147,
                "action": "enter",
                "outcome": "",
                "evidence_ref": "weather_ev",
                "pnl": "",
                "metadata": json.dumps(
                    {"side": "NO", "event_slug": "highest-temperature-in-shanghai-on-april-25-2026"}
                ),
            },
            {
                "method": "weather_forecast_market_edge",
                "domain": "weather",
                "timestamp": "2026-04-24 17:00:04+0000",
                "market_id": "highest-temperature-in-shanghai-on-april-25-2026-22c",
                "target": "22掳C NO",
                "market_prob": 0.7,
                "model_prob": 0.8,
                "data_score": 0.1,
                "news_score": 0.0,
                "edge": 0.1,
                "action": "enter",
                "outcome": "",
                "evidence_ref": "weather_ev",
                "pnl": "",
                "metadata": json.dumps(
                    {"side": "NO", "event_slug": "highest-temperature-in-shanghai-on-april-25-2026"}
                ),
            },
        ]
    ).to_csv(signals, index=False)

    reports = load_weather_reports(
        signals_csv=signals,
        actual_outcomes={"highest-temperature-in-shanghai-on-april-25-2026": "21°C"},
    )

    assert [report.outcome for report in reports] == ["LOSE", "WIN"]
    assert reports[0].metadata["yes_outcome"] == 1.0
    assert reports[1].metadata["yes_outcome"] == 0.0


def test_btc_outcome_fetcher_writes_csv_and_resolver_reads(tmp_path) -> None:
    signals = tmp_path / "signals.csv"
    out = tmp_path / "btc_5m_outcome.csv"
    pd.DataFrame(
        [
            {
                "generated_at": "2026-05-06T18:23:27Z",
                "domain": "btc",
                "target": "BTC near-term",
                "direction_score": -0.1,
                "probability_delta": 0.02,
                "relevance": 0.5,
                "confidence": 0.9,
                "metadata": json.dumps(
                    {
                        "market_id": "btc_5m_up_down",
                        "time_window": {"as_of": "2026-05-06T18:23:27Z"},
                    }
                ),
                "top_evidence": "[]",
                "outcome_scores": "{}",
            }
        ]
    ).to_csv(signals, index=False)

    rows = build_btc_outcome_rows(
        signals,
        fetcher=lambda as_of, end_at: {
            "start_price": 100.0,
            "end_price": 99.0,
            "source": "test",
            "source_symbol": "BTC-TEST",
        },
    )
    write_btc_outcome_csv(rows, out)

    outcomes = load_yes_outcomes_csv(out)
    assert outcomes == {"btc_5m_up_down": 0.0}


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
