from __future__ import annotations

import json

import pandas as pd

from research.adapters.acy_news_adapter import load_acy_news_reports
from research.adapters.cs2_adapter import load_cs2_reports
from research.adapters.weather_adapter import load_weather_reports
from research.evaluation.outcomes import load_yes_outcomes_csv
from research.run.build_btc_multi_market_signals import build_btc_multi_market_signal_rows
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


def test_acy_news_adapter_loads_multi_domain_output_dirs(tmp_path) -> None:
    for folder, domain in [
        ("outputs_btc_window", "btc"),
        ("outputs_cs2_window", "cs2"),
        ("outputs_weather_window", "weather"),
    ]:
        output_dir = tmp_path / folder
        output_dir.mkdir()
        pd.DataFrame(
            [
                {
                    "domain": "" if domain == "cs2" else domain,
                    "timestamp": f"2026-05-01T00:00:00Z",
                    "market_id": f"{domain}-market",
                    "target": f"{domain} target",
                    "market_prob": 0.5,
                    "direction_score": -0.2 if domain == "weather" else 0.2,
                    "probability_delta": 0.05,
                    "relevance": 0.4,
                    "confidence": 0.5,
                    "top_evidence": json.dumps([{"id": f"{domain}-ev"}]),
                    "metadata": "{}",
                }
            ]
        ).to_csv(output_dir / "signals.csv", index=False)
        (output_dir / "evidence.jsonl").write_text("", encoding="utf-8")

    reports = load_acy_news_reports(
        news_output_dirs=[
            tmp_path / "outputs_btc_window",
            tmp_path / "outputs_cs2_window",
            tmp_path / "outputs_weather_window",
        ]
    )

    assert {report.domain for report in reports} == {"btc", "cs2", "weather"}
    assert {report.evidence_ref for report in reports} == {"btc-ev", "cs2-ev", "weather-ev"}
    assert all(report.news_score == 0.2 for report in reports)


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


def test_btc_multi_market_builder_expands_source_signal(tmp_path) -> None:
    signals = tmp_path / "signals.csv"
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
                        "market_prob": 0.5,
                        "time_window": {"as_of": "2026-05-06T18:23:27Z"},
                    }
                ),
                "top_evidence": json.dumps([{"id": "ev_btc_001"}]),
                "outcome_scores": json.dumps({"long": -0.1, "short": 0.1}),
            }
        ]
    ).to_csv(signals, index=False)

    rows = build_btc_multi_market_signal_rows(
        signals,
        decision_times=["2026-05-06T18:25:00Z", "2026-05-06T18:30:00Z"],
    )

    assert len(rows) == 2
    assert {row["action"] for row in rows} == {"AUTO"}
    metadata = [json.loads(row["metadata"]) for row in rows]
    assert {item["market_id"] for item in metadata} == {
        "btc_5m_up_down_20260506T182500Z",
        "btc_5m_up_down_20260506T183000Z",
    }
    assert metadata[0]["time_window"]["as_of"] == "2026-05-06T18:25:00Z"
    assert metadata[0]["market_window"]["end_at"] == "2026-05-06T18:30:00Z"
    assert metadata[0]["source_signal_market_id"] == "btc_5m_up_down"
    assert metadata[0]["rolling_window_count"] == 2


def test_btc_outcome_fetcher_handles_multiple_markets(tmp_path) -> None:
    signals = tmp_path / "signals.csv"
    rows = []
    for as_of in ["2026-05-06T18:25:00Z", "2026-05-06T18:30:00Z"]:
        rows.append(
            {
                "generated_at": as_of,
                "domain": "btc",
                "target": "BTC near-term",
                "direction_score": 0.1,
                "probability_delta": 0.02,
                "relevance": 0.5,
                "confidence": 0.9,
                "metadata": json.dumps(
                    {
                        "market_id": f"btc_5m_up_down_{as_of[11:16].replace(':', '')}",
                        "time_window": {"as_of": as_of},
                    }
                ),
                "top_evidence": "[]",
                "outcome_scores": "{}",
            }
        )
    pd.DataFrame(rows).to_csv(signals, index=False)

    outcome_rows = build_btc_outcome_rows(
        signals,
        fetcher=lambda as_of, end_at: {
            "start_price": 100.0,
            "end_price": 101.0 if as_of.minute == 25 else 99.0,
            "source": "test",
            "source_symbol": "BTC-TEST",
        },
    )

    assert [row["winning_side"] for row in outcome_rows] == ["YES", "NO"]
    assert [row["market_id"] for row in outcome_rows] == ["btc_5m_up_down_1825", "btc_5m_up_down_1830"]


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
