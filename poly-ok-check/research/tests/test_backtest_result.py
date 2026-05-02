from __future__ import annotations

import pandas as pd

from research.backtest.backtest_env import BacktestEnv
from research.backtest.execution import LatencyModel
from research.core.data_simulator import DataSimulator, build_mock_match_channels
from research.schemas.risk_context import RiskContext


def test_backtest_result_contains_timeline_orders_fills_and_summary() -> None:
    simulator = DataSimulator(latency_offset_secs=30, window_secs=10)
    packages = simulator.build_data_packages(build_mock_match_channels(), match_id="m1")
    market_df = pd.DataFrame(
        [
            {"timestamp_s": 35.0, "market_id": "m1", "token_id": "t1", "bids": ["0.47@1000"], "asks": ["0.51@1000"]},
            {"timestamp_s": 45.0, "market_id": "m1", "token_id": "t1", "bids": ["0.58@1000"], "asks": ["0.62@1000"]},
            {"timestamp_s": 55.0, "market_id": "m1", "token_id": "t1", "bids": ["0.65@1000"], "asks": ["0.69@1000"]},
        ]
    )
    risk = RiskContext(
        equity=10_000.0,
        cash=10_000.0,
        current_position_side=None,
        current_position_size=0.0,
        drawdown=0.0,
        event_tier="S",
        allow_new_entry=True,
        reduce_only=False,
    )

    result = BacktestEnv(latency_model=LatencyModel(base_latency_ms=0.0, jitter_ms=0.0)).run_match_replay_result(
        packages,
        market_df,
        risk,
        outcomes={"t1": 1.0},
    )

    assert not result.timeline.empty
    assert not result.orders.empty
    assert not result.fills.empty
    for key in {
        "final_equity",
        "total_pnl",
        "realized_pnl",
        "unrealized_pnl",
        "max_drawdown",
        "trade_count",
        "fill_count",
        "fees_paid",
    }:
        assert key in result.summary
