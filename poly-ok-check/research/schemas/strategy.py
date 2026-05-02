from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from research.backtest.portfolio import PortfolioState
from research.schemas.market import MarketSnapshotFrame


@dataclass(slots=True)
class StrategyContext:
    timestamp_s: float
    run_config: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


@dataclass(slots=True)
class StrategyDecision:
    target_side: str
    target_notional_usd: float
    reason: str = ""
    metadata: dict = field(default_factory=dict)


class Strategy(Protocol):
    def on_snapshot(
        self,
        snapshot: MarketSnapshotFrame,
        portfolio: PortfolioState,
        context: StrategyContext,
    ) -> list[StrategyDecision]:
        ...
