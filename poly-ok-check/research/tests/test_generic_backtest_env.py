from __future__ import annotations

import pandas as pd

from research.backtest.execution import LatencyModel
from research.backtest.generic_env import GenericMarketBacktestEnv
from research.backtest.report import write_backtest_report
from research.schemas.risk_context import RiskContext
from research.strategy.generic import ProbabilityCsvStrategy, TargetCsvStrategy


def make_market_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"timestamp_s": 10.0, "market_id": "m1", "token_id": "t1", "bids": ["0.49@1000"], "asks": ["0.51@1000"]},
            {"timestamp_s": 20.0, "market_id": "m1", "token_id": "t1", "bids": ["0.59@1000"], "asks": ["0.61@1000"]},
            {"timestamp_s": 30.0, "market_id": "m1", "token_id": "t1", "bids": ["0.69@1000"], "asks": ["0.71@1000"]},
        ]
    )


def make_risk() -> RiskContext:
    return RiskContext(
        equity=10_000.0,
        cash=10_000.0,
        current_position_side=None,
        current_position_size=0.0,
        drawdown=0.0,
        event_tier="generic",
        allow_new_entry=True,
        reduce_only=False,
    )


def test_generic_env_runs_probability_strategy_without_cs2(tmp_path) -> None:
    signal_path = tmp_path / "prob.csv"
    pd.DataFrame([{"timestamp_s": 1.0, "fair_prob": 0.80}]).to_csv(signal_path, index=False)
    strategy = ProbabilityCsvStrategy(signal_path, position_size=100.0)

    result = GenericMarketBacktestEnv(latency_model=LatencyModel(0.0, 0.0)).run(
        make_market_df(),
        strategy,
        make_risk(),
        outcome=1.0,
    )

    assert not result.timeline.empty
    assert not result.orders.empty
    assert not result.fills.empty
    assert result.summary["fill_count"] > 0
    assert "source_quality" in result.summary


def test_generic_env_runs_target_strategy_enter_and_exit(tmp_path) -> None:
    signal_path = tmp_path / "target.csv"
    pd.DataFrame(
        [
            {"timestamp_s": 1.0, "target_side": "YES", "target_notional_usd": 100.0},
            {"timestamp_s": 25.0, "target_side": "FLAT", "target_notional_usd": 0.0},
        ]
    ).to_csv(signal_path, index=False)

    result = GenericMarketBacktestEnv(latency_model=LatencyModel(0.0, 0.0)).run(
        make_market_df(),
        TargetCsvStrategy(signal_path),
        make_risk(),
    )

    assert set(result.orders["action"]) == {"BUY", "SELL"}
    assert result.summary["trade_count"] == 2


def test_write_backtest_report_creates_expected_files(tmp_path) -> None:
    signal_path = tmp_path / "prob.csv"
    pd.DataFrame([{"timestamp_s": 1.0, "fair_prob": 0.80}]).to_csv(signal_path, index=False)
    market_df = make_market_df()
    result = GenericMarketBacktestEnv(latency_model=LatencyModel(0.0, 0.0)).run(
        market_df,
        ProbabilityCsvStrategy(signal_path),
        make_risk(),
        outcome=1.0,
    )

    run_dir = write_backtest_report(result, market_df, {"run_id": "test-run"}, tmp_path / "runs")

    for name in {
        "summary.json",
        "timeline.csv",
        "orders.csv",
        "fills.csv",
        "trades.csv",
        "market_frames.csv",
        "quality.json",
        "config.json",
    }:
        assert (run_dir / name).exists()
