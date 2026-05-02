from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass(slots=True)
class TargetPosition:
    market_id: str
    token_id: str
    side: str
    target_notional_usd: float
    reason: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class SimulatedOrder:
    order_id: str
    decision_ts_s: float
    execution_ts_s: float
    market_id: str
    token_id: str
    side: str
    action: str
    requested_notional_usd: float = 0.0
    requested_qty: float = 0.0
    status: str = "created"
    reason: str = ""
    latency_ms: float = 0.0
    unfilled_notional_usd: float = 0.0

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "decision_ts_s": self.decision_ts_s,
            "execution_ts_s": self.execution_ts_s,
            "market_id": self.market_id,
            "token_id": self.token_id,
            "side": self.side,
            "action": self.action,
            "requested_notional_usd": self.requested_notional_usd,
            "requested_qty": self.requested_qty,
            "status": self.status,
            "reason": self.reason,
            "latency_ms": self.latency_ms,
            "unfilled_notional_usd": self.unfilled_notional_usd,
        }


@dataclass(slots=True)
class Fill:
    order_id: str
    ts_s: float
    market_id: str
    token_id: str
    side: str
    action: str
    qty: float
    avg_price: float
    notional_usd: float
    fee_usd: float
    slippage_usd: float

    def to_dict(self) -> dict:
        return {
            "order_id": self.order_id,
            "ts_s": self.ts_s,
            "market_id": self.market_id,
            "token_id": self.token_id,
            "side": self.side,
            "action": self.action,
            "qty": self.qty,
            "avg_price": self.avg_price,
            "notional_usd": self.notional_usd,
            "fee_usd": self.fee_usd,
            "slippage_usd": self.slippage_usd,
        }


@dataclass(slots=True)
class BacktestResult:
    timeline: pd.DataFrame
    orders: pd.DataFrame
    fills: pd.DataFrame
    trades: pd.DataFrame
    summary: dict
