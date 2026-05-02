from __future__ import annotations

import pandas as pd

from research.backtest.execution import ExecutionSimulator, LatencyModel
from research.backtest.outcomes import OutcomeStore
from research.backtest.portfolio import PortfolioState
from research.core.calibrator import ProbabilityCalibrator
from research.core.edge_calculator import EdgeCalculator
from research.core.market_aligner import MarketAligner
from research.market_data import normalize_market_frames
from research.models.bayesian_predictor import BayesianPredictor
from research.schemas.execution import BacktestResult, SimulatedOrder, TargetPosition
from research.schemas.market_frame import AlignedMarketFrame
from research.schemas.risk_context import RiskContext
from research.strategy.agent_commander import AgentCommander


class BacktestEnv:
    def __init__(
        self,
        predictor: BayesianPredictor | None = None,
        calibrator: ProbabilityCalibrator | None = None,
        aligner: MarketAligner | None = None,
        edge_calculator: EdgeCalculator | None = None,
        commander: AgentCommander | None = None,
        execution_simulator: ExecutionSimulator | None = None,
        latency_model: LatencyModel | None = None,
        position_size: float = 100.0,
    ):
        self.predictor = predictor or BayesianPredictor()
        self.calibrator = calibrator or ProbabilityCalibrator()
        self.aligner = aligner or MarketAligner()
        self.edge_calculator = edge_calculator or EdgeCalculator()
        self.commander = commander or AgentCommander(default_notional_usd=position_size)
        self.execution_simulator = execution_simulator or ExecutionSimulator(fee_bps=self.edge_calculator.fee_bps)
        self.latency_model = latency_model or LatencyModel()
        self.position_size = position_size

    def run_match_replay(
        self,
        packages: list,
        market_df: pd.DataFrame,
        risk_context: RiskContext,
    ) -> pd.DataFrame:
        return self.run_match_replay_result(packages, market_df, risk_context).timeline

    def run_match_replay_result(
        self,
        packages: list,
        market_df: pd.DataFrame,
        risk_context: RiskContext,
        outcomes=None,
    ) -> BacktestResult:
        canonical_market_df = normalize_market_frames(market_df)
        market_id, token_id = self._infer_market_identity(canonical_market_df)
        replay_market_df = self._filter_market(canonical_market_df, market_id, token_id)
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

        for step_index, data_package in enumerate(packages, start=1):
            model_win_prob = self.predictor.predict_proba(data_package)
            fair_win_prob = self.calibrator.transform(model_win_prob)
            aligned = self.aligner.align_one(data_package, replay_market_df)
            edge = self.edge_calculator.compute(
                fair_win_prob=fair_win_prob,
                market_implied_prob=aligned["market_implied_prob"],
                best_bid=aligned["best_bid"],
                best_ask=aligned["best_ask"],
                depth_usd=aligned["depth_usd"],
                latency_ms=aligned["market_age_ms"],
            )
            frame = AlignedMarketFrame(
                data_package=data_package,
                market_snapshot_ts_s=aligned["market_snapshot_ts_s"],
                market_age_ms=aligned["market_age_ms"],
                alignment_gap_ms=aligned["alignment_gap_ms"],
                is_stale_snapshot=aligned["is_stale_snapshot"],
                model_win_prob=model_win_prob,
                fair_win_prob=fair_win_prob,
                market_implied_prob=aligned["market_implied_prob"],
                orderbook_mid=aligned["orderbook_mid"],
                best_bid=aligned["best_bid"],
                best_ask=aligned["best_ask"],
                depth_usd=aligned["depth_usd"],
                lp_reward_estimate=aligned["lp_reward_estimate"],
                fees=edge["fees"],
                slippage_est=edge["slippage_est"],
                latency_penalty=edge["latency_penalty"],
                liquidity_penalty=edge["liquidity_penalty"],
                edge_raw=edge["edge_raw"],
                edge_net=edge["edge_net"],
            )
            live_risk = portfolio.to_risk_context(
                event_tier=risk_context.event_tier,
                allow_new_entry=risk_context.allow_new_entry,
                reduce_only=risk_context.reduce_only,
            )
            decision = self.commander.decide(frame, live_risk)
            target = self.commander.target_position(
                frame=frame,
                risk=live_risk,
                market_id=market_id,
                token_id=token_id,
                decision=decision,
            )
            order = self._order_from_target(
                target=target,
                portfolio=portfolio,
                decision_ts_s=data_package.available_ts_s,
                step_index=step_index,
            )
            fill = None
            if order is not None:
                order, fill = self.execution_simulator.execute_order(order, replay_market_df)
                orders.append(order.to_dict())
                if fill is not None:
                    portfolio.apply_fill(fill)
                    fills.append(fill.to_dict())

            mark_ts = fill.ts_s if fill is not None else data_package.available_ts_s
            portfolio.mark_to_market(replay_market_df, as_of_ts_s=mark_ts)

            row = frame.to_flat_dict()
            row["action"] = decision["action"]
            row["reason"] = decision["reason"]
            row["target_side"] = target.side if target is not None else None
            row["target_notional_usd"] = target.target_notional_usd if target is not None else 0.0
            row["order_id"] = order.order_id if order is not None else None
            row["order_status"] = order.status if order is not None else None
            row["fill_qty"] = fill.qty if fill is not None else 0.0
            row["fill_avg_price"] = fill.avg_price if fill is not None else 0.0
            row["fill_notional_usd"] = fill.notional_usd if fill is not None else 0.0
            row["current_position_side"] = portfolio.current_position_side
            row["current_position_size"] = portfolio.current_position_size
            row["cash"] = portfolio.cash
            row["equity"] = portfolio.equity
            row["realized_pnl"] = portfolio.realized_pnl
            row["unrealized_pnl"] = portfolio.unrealized_pnl
            row["fees_paid"] = portfolio.fees_paid
            row["slippage_paid"] = portfolio.slippage_paid
            row["drawdown"] = portfolio.drawdown
            rows.append(row)

        outcome_store = OutcomeStore.from_any(outcomes)
        if outcome_store is not None:
            settlement_ts = max((pkg.available_ts_s for pkg in packages), default=0.0)
            portfolio.settle(outcome_store, ts_s=settlement_ts)

        orders_df = pd.DataFrame(orders)
        fills_df = pd.DataFrame(fills)
        trades_df = pd.DataFrame(portfolio.trades)
        summary = portfolio.summary()
        summary["order_count"] = int(len(orders_df))
        summary["fill_count"] = int(len(fills_df))
        summary["trade_count"] = int(len(trades_df))
        return BacktestResult(
            timeline=pd.DataFrame(rows),
            orders=orders_df,
            fills=fills_df,
            trades=trades_df,
            summary=summary,
        )

    @staticmethod
    def _infer_market_identity(market_df: pd.DataFrame) -> tuple[str, str]:
        if market_df.empty:
            return "", ""
        first = market_df.iloc[0]
        market_id = str(first.get("market_id") or "")
        token_id = str(first.get("token_id") or market_id)
        return market_id, token_id

    @staticmethod
    def _filter_market(market_df: pd.DataFrame, market_id: str, token_id: str) -> pd.DataFrame:
        if market_df.empty or not (market_id or token_id):
            return market_df
        mask = pd.Series([False] * len(market_df), index=market_df.index)
        if market_id:
            mask = mask | (market_df["market_id"] == market_id)
        if token_id:
            mask = mask | (market_df["token_id"] == token_id)
        return market_df[mask].reset_index(drop=True)

    def _order_from_target(
        self,
        target: TargetPosition | None,
        portfolio: PortfolioState,
        decision_ts_s: float,
        step_index: int,
    ) -> SimulatedOrder | None:
        if target is None:
            return None
        latency_ms = self.latency_model.sample_latency_ms()
        execution_ts_s = decision_ts_s + latency_ms / 1000.0
        active = portfolio.active_position()

        if target.side == "FLAT":
            if active is None:
                return None
            return SimulatedOrder(
                order_id=f"sim-{step_index}",
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
                order_id=f"sim-{step_index}",
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
            order_id=f"sim-{step_index}",
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
