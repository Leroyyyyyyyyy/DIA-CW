from __future__ import annotations

from pathlib import Path

import pandas as pd

from research.backtest.backtest_env import BacktestEnv
from research.core.data_simulator import DataSimulator, build_mock_match_channels
from research.schemas.risk_context import RiskContext


def build_mock_market_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "timestamp_s": 35.0,
                "market_id": "mock-market",
                "token_id": "mock-yes-token",
                "bids": [{"price": 0.47, "size": 1000.0}],
                "asks": [{"price": 0.51, "size": 1000.0}],
                "lp_reward_estimate": 0.002,
            },
            {
                "timestamp_s": 45.0,
                "market_id": "mock-market",
                "token_id": "mock-yes-token",
                "bids": [{"price": 0.58, "size": 1000.0}],
                "asks": [{"price": 0.62, "size": 1000.0}],
                "lp_reward_estimate": 0.003,
            },
            {
                "timestamp_s": 55.0,
                "market_id": "mock-market",
                "token_id": "mock-yes-token",
                "bids": [{"price": 0.65, "size": 1000.0}],
                "asks": [{"price": 0.69, "size": 1000.0}],
                "lp_reward_estimate": 0.003,
            },
        ]
    )


def main() -> None:
    _root = Path(__file__).resolve().parents[1]
    simulator = DataSimulator(latency_offset_secs=30, window_secs=10)
    packages = simulator.build_data_packages(build_mock_match_channels(), match_id="mock-match-1")
    market_df = build_mock_market_df()
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
    env = BacktestEnv()
    result = env.run_match_replay_result(packages, market_df, risk, outcomes={"mock-yes-token": 1.0})
    print("summary")
    print(result.summary)
    print("equity_tail")
    print(result.timeline.tail().to_string(index=False))
    print(f"orders={len(result.orders)} fills={len(result.fills)}")


if __name__ == "__main__":
    main()
