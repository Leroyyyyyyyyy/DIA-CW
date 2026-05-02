from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from research.market_data import normalize_market_frames
from research.schemas.execution import Fill
from research.schemas.risk_context import RiskContext


@dataclass(slots=True)
class Position:
    market_id: str
    token_id: str
    side: str
    qty: float
    avg_price: float

    @property
    def cost_basis(self) -> float:
        return self.qty * self.avg_price


@dataclass(slots=True)
class PortfolioState:
    equity: float
    cash: float
    current_position_side: str | None = None
    current_position_size: float = 0.0
    drawdown: float = 0.0
    initial_equity: float | None = None
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    fees_paid: float = 0.0
    slippage_paid: float = 0.0
    positions: dict[tuple[str, str, str], Position] = field(default_factory=dict)
    trades: list[dict] = field(default_factory=list)
    last_marks: dict[tuple[str, str, str], float] = field(default_factory=dict)
    max_equity: float = 0.0

    def __post_init__(self) -> None:
        if self.initial_equity is None:
            self.initial_equity = self.equity
        self.max_equity = max(self.max_equity, self.equity)

    def to_risk_context(self, event_tier: str, allow_new_entry: bool = True, reduce_only: bool = False) -> RiskContext:
        side = self.current_position_side
        size = self.current_position_size
        if self.positions:
            first = next(iter(self.positions.values()))
            side = first.side
            size = first.qty
        return RiskContext(
            equity=self.equity,
            cash=self.cash,
            current_position_side=side,
            current_position_size=size,
            drawdown=self.drawdown,
            event_tier=event_tier,
            allow_new_entry=allow_new_entry,
            reduce_only=reduce_only,
        )

    def apply_decision(self, action: str, position_size: float = 1.0) -> None:
        if action == "ENTER_YES":
            self.current_position_side = "YES"
            self.current_position_size = position_size
        elif action == "ENTER_NO":
            self.current_position_side = "NO"
            self.current_position_size = position_size
        elif action == "EXIT":
            self.current_position_side = None
            self.current_position_size = 0.0

    def get_position(self, market_id: str, token_id: str, side: str) -> Position | None:
        return self.positions.get(self._key(market_id, token_id, side))

    def active_position(self) -> Position | None:
        if not self.positions:
            return None
        return next(iter(self.positions.values()))

    def apply_fill(self, fill: Fill) -> None:
        key = self._key(fill.market_id, fill.token_id, fill.side)
        self.fees_paid += fill.fee_usd
        self.slippage_paid += fill.slippage_usd

        if fill.action == "BUY":
            existing = self.positions.get(key)
            if existing is None:
                self.positions[key] = Position(
                    market_id=fill.market_id,
                    token_id=fill.token_id,
                    side=fill.side,
                    qty=fill.qty,
                    avg_price=fill.avg_price,
                )
            else:
                new_qty = existing.qty + fill.qty
                existing.avg_price = ((existing.qty * existing.avg_price) + fill.notional_usd) / max(new_qty, 1e-12)
                existing.qty = new_qty
            self.cash -= fill.notional_usd + fill.fee_usd
        elif fill.action == "SELL":
            existing = self.positions.get(key)
            if existing is None:
                return
            sell_qty = min(fill.qty, existing.qty)
            sell_notional = sell_qty * fill.avg_price
            self.cash += sell_notional - fill.fee_usd
            self.realized_pnl += (fill.avg_price - existing.avg_price) * sell_qty - fill.fee_usd
            existing.qty -= sell_qty
            if existing.qty <= 1e-9:
                del self.positions[key]
        else:
            return

        self.trades.append(fill.to_dict())
        self._sync_legacy_position_fields()

    def mark_to_market(self, market_df: pd.DataFrame, as_of_ts_s: float) -> None:
        frames = normalize_market_frames(market_df)
        mtm_value = 0.0
        unrealized = 0.0
        for key, position in self.positions.items():
            market_id, token_id, _side = key
            eligible = frames[
                ((frames["token_id"] == token_id) | (frames["market_id"] == market_id))
                & (frames["timestamp_s"] <= as_of_ts_s)
            ].sort_values("timestamp_s")
            mark = self.last_marks.get(key, 0.0)
            if not eligible.empty:
                snapshot = eligible.iloc[-1]
                mark = float(snapshot["best_bid"]) if float(snapshot["best_bid"]) > 0.0 else float(snapshot["orderbook_mid"])
                self.last_marks[key] = mark
            value = position.qty * mark
            mtm_value += value
            unrealized += value - position.cost_basis

        self.unrealized_pnl = unrealized
        self.equity = self.cash + mtm_value
        self.max_equity = max(self.max_equity, self.equity)
        if self.max_equity > 0.0:
            self.drawdown = max((self.max_equity - self.equity) / self.max_equity, 0.0)

    def settle(self, outcome_store, ts_s: float) -> None:
        for key, position in list(self.positions.items()):
            payout = outcome_store.get_payout(position.market_id, position.token_id, position.side)
            if payout is None:
                continue
            proceeds = position.qty * payout
            self.cash += proceeds
            self.realized_pnl += (payout - position.avg_price) * position.qty
            self.trades.append(
                {
                    "order_id": "settlement",
                    "ts_s": ts_s,
                    "market_id": position.market_id,
                    "token_id": position.token_id,
                    "side": position.side,
                    "action": "SETTLE",
                    "qty": position.qty,
                    "avg_price": payout,
                    "notional_usd": proceeds,
                    "fee_usd": 0.0,
                    "slippage_usd": 0.0,
                }
            )
            del self.positions[key]
        self.unrealized_pnl = 0.0
        self.equity = self.cash
        self.max_equity = max(self.max_equity, self.equity)
        self._sync_legacy_position_fields()

    def summary(self) -> dict:
        final_equity = self.equity
        return {
            "initial_equity": float(self.initial_equity or 0.0),
            "final_equity": float(final_equity),
            "total_pnl": float(final_equity - (self.initial_equity or 0.0)),
            "realized_pnl": float(self.realized_pnl),
            "unrealized_pnl": float(self.unrealized_pnl),
            "max_drawdown": float(self.drawdown),
            "fees_paid": float(self.fees_paid),
            "slippage_paid": float(self.slippage_paid),
            "cash": float(self.cash),
            "gross_exposure": float(sum(position.cost_basis for position in self.positions.values())),
        }

    @staticmethod
    def _key(market_id: str, token_id: str, side: str) -> tuple[str, str, str]:
        return (str(market_id), str(token_id), side.upper())

    def _sync_legacy_position_fields(self) -> None:
        active = self.active_position()
        if active is None:
            self.current_position_side = None
            self.current_position_size = 0.0
            return
        self.current_position_side = active.side
        self.current_position_size = active.qty
