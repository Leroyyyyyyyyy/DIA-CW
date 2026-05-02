from dataclasses import dataclass


@dataclass(slots=True)
class CostConfig:
    fee_bps: float = 100.0
    slippage_coef: float = 0.5
    latency_penalty_coef: float = 0.01
    liquidity_penalty_coef: float = 0.01
    min_depth_usd: float = 500.0

