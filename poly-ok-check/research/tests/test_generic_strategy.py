from __future__ import annotations

import pandas as pd
import pytest

from research.backtest.portfolio import PortfolioState
from research.schemas.market import MarketSnapshotFrame
from research.schemas.strategy import StrategyContext
from research.strategy.generic import ProbabilityCsvStrategy, TargetCsvStrategy, load_signal_csv, load_strategy_from_path


def make_snapshot(ts: float = 10.0) -> MarketSnapshotFrame:
    return MarketSnapshotFrame(
        timestamp_s=ts,
        market_id="m1",
        token_id="t1",
        best_bid=0.49,
        best_ask=0.51,
        orderbook_mid=0.50,
        spread=0.02,
        depth_usd=1000.0,
        bids=[{"price": 0.49, "size": 100.0}],
        asks=[{"price": 0.51, "size": 100.0}],
        source="test",
    )


def test_probability_csv_strategy_validates_and_enters(tmp_path) -> None:
    path = tmp_path / "signals.csv"
    pd.DataFrame([{"timestamp_s": 1.0, "fair_prob": 0.70, "reason": "edge"}]).to_csv(path, index=False)
    strategy = ProbabilityCsvStrategy(path, entry_threshold=0.03, position_size=50.0)

    decisions = strategy.on_snapshot(
        make_snapshot(),
        PortfolioState(equity=1000.0, cash=1000.0),
        StrategyContext(timestamp_s=10.0),
    )

    assert decisions[0].target_side == "YES"
    assert decisions[0].target_notional_usd == 50.0


def test_target_csv_strategy_validates_columns(tmp_path) -> None:
    path = tmp_path / "bad.csv"
    pd.DataFrame([{"timestamp_s": 1.0, "target_side": "YES"}]).to_csv(path, index=False)

    with pytest.raises(ValueError):
        load_signal_csv(path, mode="target")


def test_target_csv_strategy_replays_latest_signal(tmp_path) -> None:
    path = tmp_path / "signals.csv"
    pd.DataFrame(
        [
            {"timestamp_s": 1.0, "target_side": "YES", "target_notional_usd": 100.0},
            {"timestamp_s": 20.0, "target_side": "FLAT", "target_notional_usd": 0.0},
        ]
    ).to_csv(path, index=False)
    strategy = TargetCsvStrategy(path)

    early = strategy.on_snapshot(make_snapshot(10.0), PortfolioState(1000.0, 1000.0), StrategyContext(10.0))
    late = strategy.on_snapshot(make_snapshot(25.0), PortfolioState(1000.0, 1000.0), StrategyContext(25.0))

    assert early[0].target_side == "YES"
    assert late[0].target_side == "FLAT"


def test_load_strategy_from_path(tmp_path) -> None:
    path = tmp_path / "my_strategy.py"
    path.write_text(
        "from research.schemas.strategy import StrategyDecision\n"
        "class MyStrategy:\n"
        "    def on_snapshot(self, snapshot, portfolio, context):\n"
        "        return [StrategyDecision('YES', 10.0, 'loaded')]\n",
        encoding="utf-8",
    )

    strategy = load_strategy_from_path(path, "MyStrategy")
    decisions = strategy.on_snapshot(make_snapshot(), PortfolioState(1000.0, 1000.0), StrategyContext(10.0))

    assert decisions[0].reason == "loaded"
