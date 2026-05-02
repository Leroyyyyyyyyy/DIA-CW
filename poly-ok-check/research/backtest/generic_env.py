from __future__ import annotations

import pandas as pd

from research.backtest.execution import ExecutionSimulator, LatencyModel
from research.backtest.outcomes import OutcomeStore
from research.backtest.portfolio import PortfolioState
from research.market_data import normalize_market_frames
from research.schemas.execution import BacktestResult, SimulatedOrder, TargetPosition
from research.schemas.market import MarketSnapshotFrame
from research.schemas.risk_context import RiskContext
from research.schemas.strategy import Strategy, StrategyContext, StrategyDecision


class GenericMarketBacktestEnv:
    def __init__(
        self,
        execution_simulator: ExecutionSimulator | None = None,
        latency_model: LatencyModel | None = None,
    ):
        self.execution_simulator = execution_simulator or ExecutionSimulator()
        self.latency_model = latency_model or LatencyModel()

    def run(
        self,
        market_df: pd.DataFrame,
        strategy: Strategy,
        risk_context: RiskContext,
        outcome=None,
        run_config: dict | None = None,
    ) -> BacktestResult:
        replay_market_df = normalize_market_frames(market_df)
        portfolio = PortfolioState(
            equity=risk_context.equity,
            cash=risk_context.cash,
            current_position_side=risk_context.current_position_side,
            current_position_size=risk_context.current_position_size,
            drawdown=risk_context.drawdown,
        )
        rows: list[dict] = []
        orders: list[dict] = []
        fills: list[dict] = []

        for step_index, (_, row) in enumerate(replay_market_df.iterrows(), start=1):
            snapshot = MarketSnapshotFrame.from_series(row)
            context = StrategyContext(
                timestamp_s=snapshot.timestamp_s,
                run_config=run_config or {},
                metadata={"step_index": step_index},
            )
            decisions = strategy.on_snapshot(snapshot, portfolio, context)
            step_orders: list[SimulatedOrder] = []
            step_fills = []

            for decision_index, decision in enumerate(decisions, start=1):
                target = self._target_from_decision(snapshot, decision)
                order = self._order_from_target(
                    target=target,
                    portfolio=portfolio,
                    decision_ts_s=snapshot.timestamp_s,
                    order_id=f"gen-{step_index}-{decision_index}",
                )
                if order is None:
                    continue
                order, fill = self.execution_simulator.execute_order(order, replay_market_df)
                orders.append(order.to_dict())
                step_orders.append(order)
                if fill is not None:
                    portfolio.apply_fill(fill)
                    fills.append(fill.to_dict())
                    step_fills.append(fill)

            mark_ts = step_fills[-1].ts_s if step_fills else snapshot.timestamp_s
            portfolio.mark_to_market(replay_market_df, as_of_ts_s=mark_ts)

            latest_decision = decisions[-1] if decisions else None
            latest_order = step_orders[-1] if step_orders else None
            latest_fill = step_fills[-1] if step_fills else None
            rows.append(
                {
                    **snapshot.to_dict(),
                    "decision_count": len(decisions),
                    "target_side": latest_decision.target_side if latest_decision else None,
                    "target_notional_usd": latest_decision.target_notional_usd if latest_decision else 0.0,
                    "decision_reason": latest_decision.reason if latest_decision else "",
                    "order_id": latest_order.order_id if latest_order else None,
                    "order_status": latest_order.status if latest_order else None,
                    "fill_qty": latest_fill.qty if latest_fill else 0.0,
                    "fill_avg_price": latest_fill.avg_price if latest_fill else 0.0,
                    "fill_notional_usd": latest_fill.notional_usd if latest_fill else 0.0,
                    "current_position_side": portfolio.current_position_side,
                    "current_position_size": portfolio.current_position_size,
                    "cash": portfolio.cash,
                    "equity": portfolio.equity,
                    "realized_pnl": portfolio.realized_pnl,
                    "unrealized_pnl": portfolio.unrealized_pnl,
                    "fees_paid": portfolio.fees_paid,
                    "slippage_paid": portfolio.slippage_paid,
                    "drawdown": portfolio.drawdown,
                }
            )

        outcome_store = self._outcome_store(outcome, replay_market_df)
        if outcome_store is not None:
            settlement_ts = float(replay_market_df["timestamp_s"].max()) if not replay_market_df.empty else 0.0
            portfolio.settle(outcome_store, ts_s=settlement_ts)

        orders_df = pd.DataFrame(orders)
        fills_df = pd.DataFrame(fills)
        trades_df = pd.DataFrame(portfolio.trades)
        summary = portfolio.summary()
        summary["order_count"] = int(len(orders_df))
        summary["fill_count"] = int(len(fills_df))
        summary["trade_count"] = int(len(trades_df))
        summary["source_quality"] = _source_quality(replay_market_df)
        return BacktestResult(
            timeline=pd.DataFrame(rows),
            orders=orders_df,
            fills=fills_df,
            trades=trades_df,
            summary=summary,
        )

    @staticmethod
    def _target_from_decision(snapshot: MarketSnapshotFrame, decision: StrategyDecision) -> TargetPosition:
        return TargetPosition(
            market_id=snapshot.market_id,
            token_id=snapshot.token_id,
            side=decision.target_side.upper(),
            target_notional_usd=decision.target_notional_usd,
            reason=decision.reason,
            metadata=decision.metadata,
        )

    def _order_from_target(
        self,
        target: TargetPosition,
        portfolio: PortfolioState,
        decision_ts_s: float,
        order_id: str,
    ) -> SimulatedOrder | None:
        latency_ms = self.latency_model.sample_latency_ms()
        execution_ts_s = decision_ts_s + latency_ms / 1000.0
        active = portfolio.active_position()

        if target.side == "FLAT":
            if active is None:
                return None
            return SimulatedOrder(
                order_id=order_id,
                decision_ts_s=decision_ts_s,
                execution_ts_s=execution_ts_s,
                market_id=active.market_id,
                token_id=active.token_id,
                side=active.side,
                action="SELL",
                requested_notional_usd=active.cost_basis,
                requested_qty=active.qty,
                reason=target.reason,
                latency_ms=latency_ms,
            )
        if active is not None:
            if active.side == target.side:
                return None
            return SimulatedOrder(
                order_id=order_id,
                decision_ts_s=decision_ts_s,
                execution_ts_s=execution_ts_s,
                market_id=active.market_id,
                token_id=active.token_id,
                side=active.side,
                action="SELL",
                requested_notional_usd=active.cost_basis,
                requested_qty=active.qty,
                reason=f"flatten_before_{target.side.lower()}",
                latency_ms=latency_ms,
            )
        return SimulatedOrder(
            order_id=order_id,
            decision_ts_s=decision_ts_s,
            execution_ts_s=execution_ts_s,
            market_id=target.market_id,
            token_id=target.token_id,
            side=target.side,
            action="BUY",
            requested_notional_usd=target.target_notional_usd,
            requested_qty=0.0,
            reason=target.reason,
            latency_ms=latency_ms,
        )

    @staticmethod
    def _outcome_store(outcome, market_df: pd.DataFrame) -> OutcomeStore | None:
        if outcome is None:
            return None
        if isinstance(outcome, (int, float)):
            if market_df.empty:
                return None
            token_id = str(market_df.iloc[0]["token_id"])
            market_id = str(market_df.iloc[0]["market_id"])
            return OutcomeStore({token_id: float(outcome), market_id: float(outcome)})
        return OutcomeStore.from_any(outcome)


def _source_quality(market_df: pd.DataFrame) -> dict:
    if market_df.empty:
        return {"rows": 0, "partial_rows": 0, "stale_rows": 0, "sources": []}
    return {
        "rows": int(len(market_df)),
        "partial_rows": int(market_df["quality_partial"].map(bool).sum()),
        "stale_rows": int(market_df["quality_stale"].map(bool).sum()),
        "sources": sorted(str(value) for value in set(market_df["source"])),
    }
