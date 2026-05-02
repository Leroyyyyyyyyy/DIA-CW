from __future__ import annotations

import pandas as pd

from research.backtest.execution import ExecutionSimulator, LatencyModel
from research.schemas.execution import SimulatedOrder


def test_latency_model_uses_seeded_jitter() -> None:
    model = LatencyModel(base_latency_ms=500.0, jitter_ms=100.0, seed=42)
    assert round(model.sample_latency_ms(), 6) == 527.885360


def test_execution_uses_first_snapshot_after_execution_ts() -> None:
    market_df = pd.DataFrame(
        [
            {"timestamp_s": 10.0, "token_id": "t1", "bids": ["0.40@10"], "asks": ["0.50@10"]},
            {"timestamp_s": 11.0, "token_id": "t1", "bids": ["0.41@10"], "asks": ["0.60@10"]},
        ]
    )
    order = SimulatedOrder(
        order_id="o1",
        decision_ts_s=9.0,
        execution_ts_s=10.5,
        market_id="m1",
        token_id="t1",
        side="YES",
        action="BUY",
        requested_notional_usd=6.0,
    )

    executed, fill = ExecutionSimulator(fee_bps=0.0).execute_order(order, market_df)

    assert executed.status == "filled"
    assert fill is not None
    assert fill.ts_s == 11.0
    assert fill.avg_price == 0.60


def test_execution_allows_partial_fill() -> None:
    market_df = pd.DataFrame(
        [{"timestamp_s": 10.0, "token_id": "t1", "bids": ["0.40@10"], "asks": ["0.50@2"]}]
    )
    order = SimulatedOrder(
        order_id="o1",
        decision_ts_s=9.0,
        execution_ts_s=10.0,
        market_id="m1",
        token_id="t1",
        side="YES",
        action="BUY",
        requested_notional_usd=10.0,
    )

    executed, fill = ExecutionSimulator(fee_bps=0.0).execute_order(order, market_df)

    assert executed.status == "partial"
    assert fill is not None
    assert fill.qty == 2.0
    assert executed.unfilled_notional_usd == 9.0


def test_execution_expires_when_next_snapshot_is_too_late() -> None:
    market_df = pd.DataFrame(
        [{"timestamp_s": 30.0, "token_id": "t1", "bids": ["0.40@10"], "asks": ["0.50@2"]}]
    )
    order = SimulatedOrder(
        order_id="o1",
        decision_ts_s=9.0,
        execution_ts_s=10.0,
        market_id="m1",
        token_id="t1",
        side="YES",
        action="BUY",
        requested_notional_usd=10.0,
    )

    executed, fill = ExecutionSimulator(fee_bps=0.0, stale_threshold_ms=1000.0).execute_order(order, market_df)

    assert executed.status == "expired"
    assert fill is None
