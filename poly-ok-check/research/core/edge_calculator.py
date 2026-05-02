from __future__ import annotations

import numpy as np

from research.utils.time_utils import safe_float


class EdgeCalculator:
    def __init__(
        self,
        fee_bps: float = 100.0,
        slippage_coef: float = 0.5,
        latency_penalty_coef: float = 0.01,
        liquidity_penalty_coef: float = 0.01,
        min_depth_usd: float = 500.0,
    ):
        self.fee_bps = fee_bps
        self.slippage_coef = slippage_coef
        self.latency_penalty_coef = latency_penalty_coef
        self.liquidity_penalty_coef = liquidity_penalty_coef
        self.min_depth_usd = min_depth_usd

    def compute(
        self,
        fair_win_prob: float,
        market_implied_prob: float,
        best_bid: float,
        best_ask: float,
        depth_usd: float,
        latency_ms: float,
    ) -> dict:
        fair = safe_float(fair_win_prob, default=0.5)
        implied = safe_float(market_implied_prob, default=0.5)
        bid = max(safe_float(best_bid), 0.0)
        ask = max(safe_float(best_ask), 0.0)
        depth = max(safe_float(depth_usd), 0.0)
        latency = max(safe_float(latency_ms), 0.0)

        spread = max(ask - bid, 0.0)
        fees = max(self.fee_bps / 10_000.0, 0.0)
        slippage_est = max(self.slippage_coef * spread * (1.0 + 1.0 / max(depth, 1.0)), 0.0)
        latency_penalty = max(latency * self.latency_penalty_coef / 1000.0, 0.0)
        if depth < self.min_depth_usd:
            liquidity_penalty = self.liquidity_penalty_coef * ((self.min_depth_usd - depth) / max(self.min_depth_usd, 1.0))
        else:
            liquidity_penalty = 0.0

        edge_raw = fair - implied
        edge_net = edge_raw - fees - slippage_est - latency_penalty - liquidity_penalty

        values = {
            "fees": fees,
            "slippage_est": slippage_est,
            "latency_penalty": latency_penalty,
            "liquidity_penalty": liquidity_penalty,
            "edge_raw": edge_raw,
            "edge_net": edge_net,
        }
        return {key: float(np.nan_to_num(value, nan=0.0, posinf=0.0, neginf=0.0)) for key, value in values.items()}

