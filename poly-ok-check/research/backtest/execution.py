from __future__ import annotations

import random
from dataclasses import dataclass, field

import pandas as pd

from research.market_data import normalize_market_frames, parse_order_levels
from research.schemas.execution import Fill, SimulatedOrder
from research.utils.time_utils import safe_float


@dataclass(slots=True)
class LatencyModel:
    base_latency_ms: float = 500.0
    jitter_ms: float = 100.0
    seed: int = 42
    _rng: random.Random = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._rng = random.Random(self.seed)

    def sample_latency_ms(self) -> float:
        jitter = self._rng.uniform(-self.jitter_ms, self.jitter_ms) if self.jitter_ms > 0.0 else 0.0
        return max(self.base_latency_ms + jitter, 0.0)


class ExecutionSimulator:
    def __init__(self, fee_bps: float = 100.0, stale_threshold_ms: float = 15_000.0):
        self.fee_bps = fee_bps
        self.stale_threshold_ms = stale_threshold_ms

    def execute_order(
        self,
        order: SimulatedOrder,
        market_df: pd.DataFrame,
    ) -> tuple[SimulatedOrder, Fill | None]:
        frames = normalize_market_frames(market_df)
        if order.token_id:
            frames = frames[frames["token_id"] == order.token_id]
        frames = frames[frames["timestamp_s"] >= order.execution_ts_s].sort_values("timestamp_s")
        if frames.empty:
            order.status = "expired"
            order.reason = order.reason or "no_snapshot_after_execution_ts"
            order.unfilled_notional_usd = order.requested_notional_usd
            return order, None

        snapshot = frames.iloc[0]
        wait_ms = (float(snapshot["timestamp_s"]) - order.execution_ts_s) * 1000.0
        if wait_ms > self.stale_threshold_ms:
            order.status = "expired"
            order.reason = order.reason or "snapshot_after_execution_too_late"
            order.unfilled_notional_usd = order.requested_notional_usd
            return order, None
        if bool(snapshot.get("quality_stale", False)):
            order.status = "skipped"
            order.reason = order.reason or "stale_snapshot"
            order.unfilled_notional_usd = order.requested_notional_usd
            return order, None

        if order.action == "BUY":
            fill = self._walk_buy(order, snapshot)
        elif order.action == "SELL":
            fill = self._walk_sell(order, snapshot)
        else:
            order.status = "skipped"
            order.reason = order.reason or "unsupported_action"
            return order, None

        if fill is None:
            order.status = "skipped"
            order.reason = order.reason or "empty_book_side"
            order.unfilled_notional_usd = order.requested_notional_usd
            return order, None

        if order.action == "SELL":
            unfilled_qty = max(order.requested_qty - fill.qty, 0.0)
            order.unfilled_notional_usd = unfilled_qty * fill.avg_price
            order.status = "filled" if unfilled_qty <= 1e-9 else "partial"
        else:
            requested_notional = order.requested_notional_usd
            order.unfilled_notional_usd = max(requested_notional - fill.notional_usd, 0.0)
            order.status = "filled" if order.unfilled_notional_usd <= 1e-9 else "partial"
        return order, fill

    def _walk_buy(self, order: SimulatedOrder, snapshot: pd.Series) -> Fill | None:
        asks = parse_order_levels(snapshot.get("asks"), side="ask")
        if not asks or order.requested_notional_usd <= 0.0:
            return None
        remaining = order.requested_notional_usd
        qty = 0.0
        notional = 0.0
        for level in asks:
            price = level["price"]
            available_qty = level["size"]
            level_notional = price * available_qty
            take_notional = min(remaining, level_notional)
            if take_notional <= 0.0:
                continue
            take_qty = take_notional / price
            qty += take_qty
            notional += take_notional
            remaining -= take_notional
            if remaining <= 1e-9:
                break
        return self._fill_from_execution(order, snapshot, qty, notional)

    def _walk_sell(self, order: SimulatedOrder, snapshot: pd.Series) -> Fill | None:
        bids = parse_order_levels(snapshot.get("bids"), side="bid")
        if not bids or order.requested_qty <= 0.0:
            return None
        remaining_qty = order.requested_qty
        qty = 0.0
        notional = 0.0
        for level in bids:
            price = level["price"]
            take_qty = min(remaining_qty, level["size"])
            if take_qty <= 0.0:
                continue
            qty += take_qty
            notional += take_qty * price
            remaining_qty -= take_qty
            if remaining_qty <= 1e-9:
                break
        return self._fill_from_execution(order, snapshot, qty, notional)

    def _fill_from_execution(
        self,
        order: SimulatedOrder,
        snapshot: pd.Series,
        qty: float,
        notional: float,
    ) -> Fill | None:
        if qty <= 0.0 or notional <= 0.0:
            return None
        avg_price = notional / qty
        midpoint = safe_float(snapshot.get("orderbook_mid"), default=0.0)
        if midpoint <= 0.0:
            midpoint = avg_price
        if order.action == "BUY":
            slippage = max(avg_price - midpoint, 0.0) * qty
        else:
            slippage = max(midpoint - avg_price, 0.0) * qty
        fee = notional * max(self.fee_bps, 0.0) / 10_000.0
        return Fill(
            order_id=order.order_id,
            ts_s=float(snapshot["timestamp_s"]),
            market_id=order.market_id,
            token_id=order.token_id,
            side=order.side,
            action=order.action,
            qty=float(qty),
            avg_price=float(avg_price),
            notional_usd=float(notional),
            fee_usd=float(fee),
            slippage_usd=float(slippage),
        )
