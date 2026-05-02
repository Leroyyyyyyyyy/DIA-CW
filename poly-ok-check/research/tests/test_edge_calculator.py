from __future__ import annotations

import math

from research.core.edge_calculator import EdgeCalculator


def test_edge_formula() -> None:
    calculator = EdgeCalculator(fee_bps=100.0, slippage_coef=0.0, latency_penalty_coef=0.0, liquidity_penalty_coef=0.0)
    result = calculator.compute(0.70, 0.60, 0.59, 0.61, 1000.0, 0.0)
    assert abs(result["edge_raw"] - 0.10) < 1e-9
    assert abs(result["edge_net"] - 0.09) < 1e-9


def test_positive_raw_can_be_negative_net() -> None:
    calculator = EdgeCalculator(fee_bps=100.0, slippage_coef=1.0, latency_penalty_coef=0.02, liquidity_penalty_coef=0.02, min_depth_usd=500.0)
    result = calculator.compute(0.55, 0.50, 0.45, 0.55, 50.0, 1000.0)
    assert result["edge_raw"] > 0
    assert result["edge_net"] < 0


def test_low_depth_increases_liquidity_penalty() -> None:
    calculator = EdgeCalculator(min_depth_usd=500.0)
    low = calculator.compute(0.60, 0.50, 0.49, 0.51, 100.0, 100.0)
    high = calculator.compute(0.60, 0.50, 0.49, 0.51, 1000.0, 100.0)
    assert low["liquidity_penalty"] > high["liquidity_penalty"]


def test_no_nan_outputs() -> None:
    calculator = EdgeCalculator()
    result = calculator.compute(0.60, 0.50, 0.0, 0.0, 0.0, 0.0)
    assert all(math.isfinite(value) for value in result.values())

